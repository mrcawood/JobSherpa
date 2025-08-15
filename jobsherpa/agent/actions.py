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
from jobsherpa.agent.types import ActionResult
from jobsherpa.agent.recipe_index import SimpleKeywordIndex
from jobsherpa.kb.models import SystemProfile, ApplicationRecipe
from jobsherpa.kb.dataset_index import DatasetIndex


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
        # Replace bespoke RAG plumbing with a RecipeIndex abstraction
        self.recipe_index = SimpleKeywordIndex(knowledge_base_dir)
        self.recipe_index.index()
        self.dataset_index = DatasetIndex(base_dir=knowledge_base_dir)
        self.dataset_index.index()
        # Normalize system profile to Pydantic model if possible
        self.system_profile_model: Optional[SystemProfile] = None
        if isinstance(system_config, dict):
            try:
                self.system_profile_model = SystemProfile.model_validate(system_config)  # type: ignore[attr-defined]
            except AttributeError:
                try:
                    self.system_profile_model = SystemProfile.parse_obj(system_config)  # type: ignore[attr-defined]
                except Exception:
                    self.system_profile_model = None

    def run(self, prompt: str, context: Optional[dict] = None) -> ActionResult:
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
            return ActionResult(
                message="I need a workspace to run this job. What directory should I use?",
                is_waiting=True,
                param_needed="workspace",
            )
        
        if not self.system_config:
            return ActionResult(
                message="I need a system profile to run this job. What system should I use?",
                is_waiting=True,
                param_needed="system",
            )
            
        logger.info("Agent received prompt: '%s'", prompt)

        recipe = self.recipe_index.find_best(prompt)

        if not recipe:
            logger.warning("No matching recipe found for prompt.")
            return ActionResult(message="Sorry, I don't know how to handle that.")
        
        logger.debug("Found matching recipe: %s", recipe["name"])
        # Try to normalize recipe to ApplicationRecipe for typed access
        recipe_model: Optional[ApplicationRecipe] = None
        try:
            recipe_model = ApplicationRecipe.model_validate(recipe)  # type: ignore[attr-defined]
        except AttributeError:
            try:
                recipe_model = ApplicationRecipe.parse_obj(recipe)  # type: ignore[attr-defined]
            except Exception:
                recipe_model = None
        
        job_name = recipe.get("template_args", {}).get("job_name", "jobsherpa-job")
        job_workspace = None

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
                        defaults_dict = defaults_obj.model_dump(exclude_none=True)  # v2
                    except AttributeError:
                        defaults_dict = defaults_obj.dict(exclude_none=True)  # v1
                    default_context.update(defaults_dict)
                elif isinstance(self.user_config, dict) and "defaults" in self.user_config:
                    default_context.update(self.user_config["defaults"])
            
            # Merge defaults, allowing conversational context to override
            for key, value in default_context.items():
                template_context.setdefault(key, value)
            
            # Add recipe-specific args, which have the highest precedence
            template_context.update(recipe.get("template_args", {}))

            # Integrate KB-derived fields
            # System: module init, launcher, partition fallback
            if self.system_profile_model:
                # module init commands for environment setup
                if self.system_profile_model.module_init:
                    template_context.setdefault("module_init", self.system_profile_model.module_init)
                # launcher (e.g., ibrun/srun)
                if self.system_profile_model.commands.launcher:
                    template_context.setdefault("launcher", self.system_profile_model.commands.launcher)
                # partition fallback
                if not template_context.get("partition") and self.system_profile_model.available_partitions:
                    template_context["partition"] = self.system_profile_model.available_partitions[0]

            # Application: module loads
            if recipe_model and recipe_model.module_loads:
                template_context.setdefault("module_loads", recipe_model.module_loads)

            # Dataset: resolve from prompt, apply resource hints
            dataset_profile = self.dataset_index.resolve(prompt)
            if dataset_profile:
                hints = dataset_profile.resource_hints or {}
                template_context.setdefault("nodes", hints.get("nodes"))
                template_context.setdefault("time", hints.get("time"))

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
                return ActionResult(message=question, is_waiting=True, param_needed=param_needed)
            
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
                return ActionResult(message=f"Error: Template '{recipe['template']}' not found.")
            except Exception as e:
                logger.error("Error rendering template: %s", e, exc_info=True)
                return ActionResult(message=f"Error rendering template: {e}", error=str(e))
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
            if job_workspace:
                job_dir_to_register = str(job_workspace.job_dir)
            else:
                job_dir_to_register = self.workspace_manager.base_path
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
            
            self.job_history.register_job(
                job_id=slurm_job_id,
                job_name=job_name,
                job_directory=job_dir_to_register,
                output_parser_info=output_parser
            )
            logger.info("Job %s submitted successfully.", slurm_job_id)
            response = f"Found recipe '{recipe['name']}'.\nJob submitted successfully with ID: {slurm_job_id}"
            return ActionResult(message=response, job_id=slurm_job_id, is_waiting=False)

        logger.info("Execution finished, but no job ID was parsed.")
        response = f"Found recipe '{recipe['name']}'.\nExecution result: {execution_result}"
        return ActionResult(message=response, is_waiting=False)

    # Legacy RAG helpers removed in favor of RecipeIndex

    def _parse_job_id(self, output: str) -> Optional[str]:
        """Parses a job ID from a string using regex."""
        match = re.search(r"Submitted batch job (\S+)", output)
        if match:
            return match.group(1)
        return None

class QueryHistoryAction:
    def __init__(self, job_history: JobHistory):
        self.job_history = job_history

    def run(self, prompt: str) -> str:
        # Simple dispatcher based on flexible regex matching
        prompt_lower = prompt.lower()
        logger.debug("QueryHistoryAction received prompt: %s", prompt)
        if re.search(r"(?=.*status)(?=.*last)", prompt_lower):
            logger.debug("Matched last status query")
            return self._get_last_job_status()
        elif re.search(r"(?=.*result)(?=.*last)", prompt_lower):
            logger.debug("Matched last result query")
            return self._get_last_job_result()
        
        job_id_match = re.search(r"job\s+(\d+)", prompt_lower)
        if job_id_match:
            job_id = job_id_match.group(1)
            logger.debug("Matched job by id query for job_id=%s", job_id)
            return self._get_job_by_id_summary(job_id)

        return "Sorry, I'm not sure how to answer that."

    def _get_last_job_status(self) -> str:
        """
        Retrieves the status of the most recent job.
        
        This tool finds the last job recorded in the history, actively checks its
        current status with the scheduler, and returns a formatted string.
        
        Returns:
            A string describing the job's status, or a message if no jobs are found.
        """
        latest_job = self.job_history.get_latest_job()
        logger.debug("Latest job for status lookup: %s", latest_job.get('job_id') if latest_job else None)
        if not latest_job:
            return "I can't find any jobs in your history."
            
        job_id = latest_job['job_id']
        current_status = self.job_history.get_status(job_id)
        logger.info("Latest job %s current status: %s", job_id, current_status)
        
        return f"The status of job {job_id} is {current_status}."
        
    def _get_last_job_result(self) -> str:
        """
        Retrieves the result of the most recent job.
        
        This tool finds the last job recorded in the history and returns its
        stored result. It does not actively check the job's status.
        
        Returns:
            A string describing the job's result, or a message if no jobs are found.
        """
        latest_job_id = self.job_history.get_latest_job_id()
        logger.debug("Latest job id for result lookup: %s", latest_job_id)
        if not latest_job_id:
            return "I can't find any jobs in your history."
        
        # Actively refresh status and attempt parsing if job is terminal
        current_status = self.job_history.check_job_status(latest_job_id)
        logger.debug("Refreshed status for %s: %s", latest_job_id, current_status)
        result = self.job_history.get_result(latest_job_id)
        if result is None:
            logger.debug("Result missing after status refresh; trying direct parse from output file")
            result = self.job_history.try_parse_result(latest_job_id)
        logger.info("Latest job %s result after refresh/parse: %s", latest_job_id, result)
        return f"The result of job {latest_job_id} is: {result or 'Not available'}."

    def _get_job_by_id_summary(self, job_id: str) -> str:
        """
        Retrieves a comprehensive summary for a specific job ID.
        
        This tool finds the job in the history, actively checks its current
        status, and returns a formatted string containing both the status
        and any available result.
        
        Args:
            job_id: The ID of the job to summarize.
            
        Returns:
            A string containing the job summary, or a message if the job is not found.
        """
        job_info = self.job_history.get_job_by_id(job_id)
        logger.debug("Lookup job by id %s -> found: %s", job_id, bool(job_info))
        if not job_info:
            return f"Sorry, I couldn't find any information for job ID {job_id}."
            
        status = self.job_history.check_job_status(job_id)
        result = job_info.get('result')
        if result is None:
            logger.debug("Result missing for job %s; trying direct parse from output file", job_id)
            result = self.job_history.try_parse_result(job_id) or 'Not available'
        logger.info("Job %s summary: status=%s, result=%s", job_id, status, result)
        return f"Job {job_id} status is {status}. Result: {result}"
