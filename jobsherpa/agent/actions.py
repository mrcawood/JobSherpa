import re
import os
import yaml
import jinja2
import logging
from typing import Optional

from jobsherpa.agent.job_history import JobHistory
from jobsherpa.agent.workspace_manager import WorkspaceManager
from jobsherpa.agent.tool_executor import ToolExecutor
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
        user_config: dict,
        system_config: dict,
    ):
        self.job_history = job_history
        self.workspace_manager = workspace_manager
        self.tool_executor = tool_executor
        self.knowledge_base_dir = knowledge_base_dir
        self.user_config = user_config
        self.system_config = system_config
        self.rag_pipeline = self._initialize_rag_pipeline()

    def run(self, prompt: str) -> tuple[str, Optional[str]]:
        """
        The main entry point for the agent to process a user prompt.
        Returns a user-facing response string and an optional job ID.
        """
        logger.info("Agent received prompt: '%s'", prompt)

        recipe = self._find_matching_recipe(prompt)

        if not recipe:
            logger.warning("No matching recipe found for prompt.")
            return "Sorry, I don't know how to handle that.", None
        
        logger.debug("Found matching recipe: %s", recipe["name"])

        if "template" in recipe:
            # Build the template rendering context
            context = {}
            # 1. Start with system defaults (if any)
            if self.system_config and "defaults" in self.system_config:
                context.update(self.system_config["defaults"])
            # 2. Add user defaults, overwriting system defaults
            if self.user_config and "defaults" in self.user_config:
                context.update(self.user_config["defaults"])
            # 3. Add recipe-specific args, overwriting user/system defaults
            context.update(recipe.get("template_args", {}))

            # Validate that all system requirements are met
            if self.system_config and "job_requirements" in self.system_config:
                missing_reqs = [
                    req for req in self.system_config["job_requirements"] if req not in context
                ]
                if missing_reqs:
                    error_msg = f"Missing required job parameters for system '{self.system_config['name']}': {', '.join(missing_reqs)}"
                    logger.error(error_msg)
                    return error_msg, None

            logger.info("Rendering script from template: %s", recipe["template"])
            
            # Ensure workspace is defined for templated jobs
            if not self.workspace_manager:
                error_msg = (
                    "Workspace must be defined in user profile for templated jobs.\n"
                    "You can set it by running: jobsherpa config set workspace /path/to/your/workspace"
                )
                logger.error(error_msg)
                return error_msg, None

            # Create a unique, isolated directory for this job run
            job_workspace = self.workspace_manager.create_job_workspace()
            logger.info("Created isolated job directory: %s", job_workspace.job_dir)

            # Add job-specific paths to the rendering context
            context["job_dir"] = str(job_workspace.job_dir)
            context["output_dir"] = str(job_workspace.output_dir)
            context["slurm_dir"] = str(job_workspace.slurm_dir)

            # Create a Jinja2 environment
            template_dir = os.path.join(self.knowledge_base_dir, '..', 'tools')
            env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
            
            try:
                template = env.get_template(recipe["template"])
                rendered_script = template.render(context)
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
                return f"Error: Template '{recipe['template']}' not found.", None
            except Exception as e:
                logger.error("Error rendering template: %s", e, exc_info=True)
                return f"Error rendering template: {e}", None
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
            # If a parser exists, prepend the output directory to its file path
            if output_parser and 'file' in output_parser:
                output_parser['file'] = os.path.join('output', output_parser['file'])
            
            self.job_history.register_job(slurm_job_id, job_dir_to_register, output_parser_info=output_parser)
            logger.info("Job %s submitted successfully.", slurm_job_id)
            response = f"Found recipe '{recipe['name']}'.\nJob submitted successfully with ID: {slurm_job_id}"
            return response, slurm_job_id

        logger.info("Execution finished, but no job ID was parsed.")
        response = f"Found recipe '{recipe['name']}'.\nExecution result: {execution_result}"
        return response, None

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
        # Placeholder for now
        pass
