import re
import os
import yaml
import jinja2
import logging
from typing import Optional, Union
from pathlib import Path

from jobsherpa.agent.job_history import JobHistory
from jobsherpa.agent.workspace_manager import WorkspaceManager
from jobsherpa.agent.tool_executor import ToolExecutor
from jobsherpa.config import UserConfig
from haystack import Pipeline
from haystack.document_stores import InMemoryDocumentStore
from haystack.nodes import BM25Retriever
from haystack import Document


logger = logging.getLogger(__name__)


class RunJobAction:
    def __init__(
        self, 
        job_history: JobHistory, 
        workspace_manager: WorkspaceManager,
        tool_executor: ToolExecutor,
        knowledge_base_dir: str,
        user_config: Union[UserConfig, dict],
        system_config: dict,
    ):
        self.job_history = job_history
        self.workspace_manager = workspace_manager
        self.tool_executor = tool_executor
        self.knowledge_base_dir = knowledge_base_dir
        self.user_config = user_config
        self.system_config = system_config
        self.rag_pipeline = self._initialize_rag_pipeline()

    def run(self, prompt: str, context: Optional[dict] = None) -> tuple[str, Optional[str], bool, Optional[str]]:
        # First, try to update the agent's configuration from the conversational context
        if context:
            if 'workspace' in context and not self.user_config.defaults.workspace:
                workspace_path = context['workspace']
                self.user_config.defaults.workspace = workspace_path
                # The workspace manager was created with the old empty path, so we update it too
                self.workspace_manager.base_path = Path(workspace_path)
                
            if 'system' in context and not self.system_config:
                system_name = context['system']
                system_config_path = os.path.join(self.knowledge_base_dir, "system", f"{system_name}.yaml")
                if os.path.exists(system_config_path):
                    with open(system_config_path, 'r') as f:
                        self.system_config = yaml.safe_load(f)
                    self.user_config.defaults.system = system_name
                else:
                    return f"I can't find a system profile named '{system_name}'. What system should I use?", None, True, "system"

        # Now, with potentially updated configs, perform the validation checks
        if not self.user_config.defaults.workspace:
            return "I need a workspace to run this job. What directory should I use?", None, True, "workspace"
        
        if not self.system_config:
            return "I need a system profile to run this job. What system should I use?", None, True, "system"
            
        logger.info("Agent received prompt: '%s'", prompt)

        recipe = self._find_matching_recipe(prompt)

        if not recipe:
            logger.warning("No matching recipe found for prompt.")
            return "Sorry, I don't know how to handle that.", None, False, None
        
        logger.debug("Found matching recipe: %s", recipe["name"])

        if "template" in recipe:
            # Build the template rendering context, starting with the conversation context
            template_context = context.copy() if context else {}
            
            # Build the default context
            default_context = {}
            if self.system_config and "defaults" in self.system_config:
                default_context.update(self.system_config["defaults"])
            if self.user_config:
                if isinstance(self.user_config, UserConfig):
                    defaults_obj = self.user_config.defaults
                    try:
                        defaults_dict = defaults_obj.model_dump(exclude_none=True)
                    except AttributeError:
                        defaults_dict = defaults_obj.dict(exclude_none=True)
                    default_context.update(defaults_dict)
                elif isinstance(self.user_config, dict) and "defaults" in self.user_config:
                    default_context.update(self.user_config["defaults"])
            
            # Merge defaults, allowing conversational context to override
            for key, value in default_context.items():
                template_context.setdefault(key, value)
            
            # Add recipe-specific args, which have the highest precedence
            template_context.update(recipe.get("template_args", {}))

            # --- 2. Validate Final Context ---
            missing_or_empty_params = []
            # We now require job_name as a standard parameter
            required_params = self.system_config.get("job_requirements", []) + ["job_name"]
            for param in required_params:
                if param not in template_context or not template_context.get(param):
                    missing_or_empty_params.append(param)
            
            if missing_or_empty_params:
                # Ask for the first missing or empty parameter
                param_needed = missing_or_empty_params[0]
                question = f"I need a value for '{param_needed}'. What should I use?"
                return question, None, True, param_needed
            
            # --- 3. Render and Submit ---
            logger.info("Rendering script from template: %s", recipe["template"])
            
            # Ensure workspace is defined for templated jobs
            if not self.workspace_manager:
                error_msg = (
                    "Workspace must be defined in user profile for templated jobs.\n"
                    "You can set it by running: jobsherpa config set workspace /path/to/your/workspace"
                )
                logger.error(error_msg)
                return error_msg, None, False, None

            # Create a unique, isolated directory for this job run
            job_name = template_context.get("job_name", "jobsherpa-run")
            job_workspace = self.workspace_manager.create_job_workspace(job_name=job_name)
            
            # Add the job directory to the context for use in templates
            template_context["job_dir"] = str(job_workspace.job_dir)

            try:
                env = jinja2.Environment(loader=jinja2.FileSystemLoader("tools"))
                template = env.get_template(recipe["template"])
                rendered_script = template.render(template_context)
                logger.debug("Rendered script content:\n%s", rendered_script)

                # Write the rendered script to a file in the isolated job directory
                with open(job_workspace.script_path, 'w') as f:
                    f.write(rendered_script)
                logger.info("Wrote rendered script to: %s", job_workspace.script_path)

                # The "tool" in a templated recipe is the command to execute the script
                submit_command = recipe["tool"]
                if self.system_config and submit_command in self.system_config.get("commands", {}):
                    submit_command = self.system_config["commands"][submit_command]

                # The ToolExecutor will now execute from within the job directory
                execution_result = self.tool_executor.execute(
                    submit_command, 
                    [job_workspace.script_path.name], 
                    workspace=str(job_workspace.job_dir)
                )

            except jinja2.TemplateNotFound:
                logger.error("Template '%s' not found in tools directory.", recipe["template"])
                return f"Error: Template '{recipe['template']}' not found.", None, False, None
            except Exception as e:
                logger.error("Error rendering template: %s", e, exc_info=True)
                return f"Error rendering template: {e}", None, False, None
        else:
            # Fallback to existing logic for non-templated recipes
            tool_name = recipe['tool']
            if self.system_config and tool_name in self.system_config.get("commands", {}):
                tool_name = self.system_config["commands"][tool_name]
            
            args = recipe.get('args', [])
            logger.debug("Executing non-templated tool: %s with args: %s", tool_name, args)
            execution_result = self.tool_executor.execute(tool_name, args, workspace=self.workspace_manager.base_path)

        slurm_job_id = self._parse_job_id(execution_result)
        if slurm_job_id:
            job_dir_to_register = str(job_workspace.job_dir) if 'job_workspace' in locals() else self.workspace_manager.base_path
            # Pass the parser info and job directory to the tracker
            output_parser = recipe.get("output_parser")

            # If a parser exists, its 'file' field might be a template. Render it.
            if output_parser and 'file' in output_parser:
                try:
                    # Create a mini-template from the file string and render it with the same context
                    file_template = jinja2.Template(output_parser['file'])
                    resolved_file = file_template.render(template_context)
                    output_parser['file'] = os.path.join('output', resolved_file)
                except jinja2.TemplateError as e:
                    logger.error("Error rendering output_parser file template: %s", e)
            
            self.job_history.register_job(slurm_job_id, job_dir_to_register, output_parser_info=output_parser)
            logger.info("Job %s submitted successfully.", slurm_job_id)
            response = f"Found recipe '{recipe['name']}'.\nJob submitted successfully with ID: {slurm_job_id}"
            return response, slurm_job_id, False, None

        logger.info("Execution finished, but no job ID was parsed.")
        response = f"Found recipe '{recipe['name']}'.\nExecution result: {execution_result}"
        return response, None, False, None

    def _initialize_rag_pipeline(self) -> Pipeline:
        """Initializes the Haystack RAG pipeline and indexes documents."""
        document_store = InMemoryDocumentStore(use_bm25=True)
        
        # Index all application recipes
        app_dir = os.path.join(self.knowledge_base_dir, "applications")
        if not os.path.isdir(app_dir):
            logger.warning("Applications directory not found for RAG indexing: %s", app_dir)
            return Pipeline() # Return empty pipeline

        docs = []
        for filename in os.listdir(app_dir):
            if filename.endswith(".yaml"):
                with open(os.path.join(app_dir, filename), 'r') as f:
                    recipe = yaml.safe_load(f)
                    # Use keywords as the content for BM25 search
                    content = " ".join(recipe.get("keywords", []))
                    doc = Document(content=content, meta=recipe)
                    docs.append(doc)
        
        if docs:
            document_store.write_documents(docs)
        
        retriever = BM25Retriever(document_store=document_store)
        pipeline = Pipeline()
        pipeline.add_node(component=retriever, name="Retriever", inputs=["Query"])
        return pipeline

    def _find_matching_recipe(self, prompt: str):
        """Finds a recipe using the Haystack RAG pipeline."""
        results = self.rag_pipeline.run(query=prompt)
        if results["documents"]:
            # The meta field of the document contains our original recipe dict
            return results["documents"][0].meta
        return None

    def _parse_job_id(self, output: str) -> Optional[str]:
        """Parses a job ID from a string using regex."""
        match = re.search(r"Submitted batch job (\S+)", output)
        if match:
            return match.group(1)
        return None

class QueryHistoryAction:
    def __init__(self, job_history: JobHistory):
        self.job_history = job_history

    def run(self, prompt: str):
        job_id = self._extract_job_id(prompt)

        if not job_id:
            return "I'm sorry, I couldn't determine which job you're asking about. Please specify a job ID."

        if job_id == "last":
            job_id = self.job_history.get_latest_job_id()
            if not job_id:
                return "I couldn't find any jobs in your history."

        status = self.job_history.get_status(job_id)
        if not status:
            return f"Sorry, I couldn't find any information for job ID {job_id}."

        result = self.job_history.get_result(job_id)
        
        if result:
            return f"The result of job {job_id} ({status}) is: {result}"
        elif status == "COMPLETED":
            return f"Job {job_id} is {status}, but a result could not be parsed."
        else:
            return f"Job {job_id} is still {status}. The result is not yet available."

    def _extract_job_id(self, prompt: str) -> Optional[str]:
        """Extracts a job ID or the keyword 'last' from the prompt."""
        prompt = prompt.lower()
        if "last" in prompt or "latest" in prompt or "recent" in prompt:
            return "last"
        
        match = re.search(r"job\s+(\d+)", prompt)
        if match:
            return match.group(1)
        
        # Simple fallback for just a number
        match = re.search(r"(\d{4,})", prompt)
        if match:
            return match.group(1)
            
        return None
