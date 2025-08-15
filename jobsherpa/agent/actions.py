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
from jobsherpa.kb.module_client import ModuleClient
from jobsherpa.kb.system_index import SystemIndex
from jobsherpa.kb.app_registry import AppRegistry
from jobsherpa.kb.site_loader import load_site_profile
from jobsherpa.kb.scheduler_loader import load_scheduler_profile


logger = logging.getLogger(__name__)

# Minimal built-in defaults to avoid file I/O during runtime where a scheduler KB
# may not be present (e.g., certain tests/mocks). The KB, if available, remains
# the single source of truth and will override these defaults when loaded.
DEFAULT_SCHEDULER_COMMANDS = {
    "slurm": {
        "submit": "sbatch",
        "status": "squeue",
        "history": "sacct",
        "cancel": "scancel",
    }
}

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
        self.system_index = SystemIndex(base_dir=knowledge_base_dir)
        self.system_index.index()
        # App registry stored under workspace/.jobsherpa/apps.json
        history_dir = os.path.dirname(job_history.history_file_path) if getattr(job_history, 'history_file_path', None) else os.path.join(os.getcwd(), ".jobsherpa")
        self.app_registry = AppRegistry(registry_path=os.path.join(history_dir, "apps.json"))
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

    def _resolve_command(self, generic_command: str) -> str:
        """
        Resolves a generic scheduler command (e.g., 'submit', 'status') to the
        concrete system command (e.g., 'sbatch', 'squeue') using the scheduler KB.
        Falls back to the generic command if resolution is not possible.
        """
        # Resolve via scheduler KB using the system's scheduler (single source of truth)
        scheduler_name: Optional[str] = None
        try:
            if isinstance(self.system_config, dict):
                scheduler_name = self.system_config.get("scheduler")
        except Exception:
            scheduler_name = None
        if not scheduler_name:
            return generic_command
        # Prefer built-in defaults where available to avoid file I/O during tests
        if scheduler_name in DEFAULT_SCHEDULER_COMMANDS:
            commands_map = DEFAULT_SCHEDULER_COMMANDS[scheduler_name]
        else:
            # Fall back to KB loader if no built-in defaults exist
            sched_profile = load_scheduler_profile(scheduler_name, base_dir=self.knowledge_base_dir)
            if not sched_profile or not getattr(sched_profile, "commands", None):
                return generic_command
            try:
                commands_map = sched_profile.commands.model_dump(exclude_none=True)  # type: ignore[attr-defined]
            except AttributeError:
                commands_map = sched_profile.commands.dict(exclude_none=True)  # type: ignore[attr-defined]
        return commands_map.get(generic_command, generic_command)

    def run(self, prompt: str, context: Optional[dict] = None) -> ActionResult:
        # First, try to update the agent's configuration from the conversational context
        if context:
            if 'workspace' in context and not self.user_config.defaults.workspace:
                # Normalize and validate workspace: expand env vars and ~, ensure exists & writable
                raw_path = context['workspace'].strip()
                expanded_path = os.path.expandvars(os.path.expanduser(raw_path))
                # Detect unresolved environment variables
                if ('$' in raw_path) and (expanded_path == raw_path or '$' in expanded_path):
                    return ActionResult(
                        message=(
                            f"I can't resolve environment variables in '{raw_path}'. "
                            f"Please provide a concrete path (e.g., /scratch/you/workspace)."
                        ),
                        is_waiting=True,
                        param_needed='workspace'
                    )
                try:
                    os.makedirs(expanded_path, exist_ok=True)
                except Exception as e:
                    return ActionResult(
                        message=(
                            f"I couldn't create or access the workspace '{raw_path}' (expanded to '{expanded_path}'). "
                            f"Please provide a writable path."
                        ),
                        is_waiting=True,
                        param_needed="workspace",
                    )
                # Update config and manager
                self.user_config.defaults.workspace = expanded_path
                self.workspace_manager.base_path = Path(expanded_path)
                
            if 'system' in context and not self.system_config:
                system_name = context['system']
                system_config_path = os.path.join(self.knowledge_base_dir, "system", f"{system_name}.yaml")
                if os.path.exists(system_config_path):
                    with open(system_config_path, 'r') as f:
                        self.system_config = yaml.safe_load(f)
                    # Always load scheduler command mappings from scheduler KB (single source of truth)
                    if isinstance(self.system_config, dict):
                        scheduler_name = self.system_config.get("scheduler")
                        if scheduler_name:
                            sched_profile = load_scheduler_profile(scheduler_name, base_dir=self.knowledge_base_dir)
                            if sched_profile and getattr(sched_profile, "commands", None):
                                try:
                                    self.system_config["commands"] = sched_profile.commands.model_dump(exclude_none=True)  # type: ignore[attr-defined]
                                except AttributeError:
                                    self.system_config["commands"] = sched_profile.commands.dict(exclude_none=True)  # type: ignore[attr-defined]
                    self.user_config.defaults.system = system_name
                else:
                    return ActionResult(
                        message=f"I can't find a system profile named '{system_name}'. What system should I use?",
                        is_waiting=True,
                        param_needed="system",
                    )

        # Site profile (optional) for org-level defaults
        # Try to infer site via system name against site listings (optional)
        site_profile = None
        # We could scan known sites and see if current system appears; keep optional for now

        # Now, with potentially updated configs, perform the validation checks
        if not self.user_config.defaults.workspace:
            return ActionResult(
                message="I need a workspace to run this job. What directory should I use?",
                is_waiting=True,
                param_needed="workspace",
            )
        
        if not self.system_config:
            # Try to resolve system from prompt
            sys_profile = self.system_index.resolve(prompt)
            if sys_profile:
                # Normalize and set
                try:
                    self.system_config = sys_profile.model_dump()  # type: ignore[attr-defined]
                except AttributeError:
                    self.system_config = sys_profile.dict()
                self.system_profile_model = sys_profile
                # Persist into user config defaults if pydantic
                try:
                    self.user_config.defaults.system = sys_profile.name.lower()
                except Exception:
                    pass
            else:
                # List available systems for convenience
                available = sorted(self.system_index._name_to_profile.keys())  # type: ignore[attr-defined]
                choices = f" Available systems: {', '.join(available)}." if available else ""
                return ActionResult(
                    message="I need a system profile to run this job. What system should I use?" + choices,
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
                if getattr(self.system_profile_model, "commands", None) and getattr(self.system_profile_model.commands, "launcher", None):
                    template_context.setdefault("launcher", self.system_profile_model.commands.launcher)
                # partition fallback
                if not template_context.get("partition") and self.system_profile_model.available_partitions:
                    template_context["partition"] = self.system_profile_model.available_partitions[0]

            # Application: module loads via ModuleClient abstraction
            if self.system_profile_model and recipe_model:
                mc = ModuleClient(system=self.system_profile_model, app=recipe_model)
                init_cmds = mc.module_init_commands()
                loads = mc.module_loads()
                if init_cmds:
                    template_context.setdefault("module_init", init_cmds)
                if loads:
                    template_context.setdefault("module_loads", loads)
                # Resolve executable path: prefer modules (PATH). If no modules, try system binding or registry.
                if not loads:
                    exe_name = (recipe_model.binary or {}).get("name") if recipe_model.binary else None
                    # Check system bindings first
                    sys_bind = (self.system_profile_model.apps or {}).get(recipe_model.name, {})
                    exe_path = sys_bind.get("exe_path") or self.app_registry.get_exe_path(self.system_profile_model.name, recipe_model.name)
                    if exe_path:
                        template_context.setdefault("wrf_exe", exe_path)
                    elif exe_name:
                        # Let PATH handle it by name
                        template_context.setdefault("wrf_exe", exe_name)

            # Dataset: resolve from prompt, apply resource hints
            dataset_profile = self.dataset_index.resolve(prompt)
            if dataset_profile:
                hints = dataset_profile.resource_hints or {}
                template_context.setdefault("nodes", hints.get("nodes"))
                template_context.setdefault("time", hints.get("time"))
                # dataset path for the current system if available
                if self.system_profile_model and dataset_profile.locations:
                    sys_name = self.system_profile_model.name
                    ds_path = dataset_profile.locations.get(sys_name)
                    if ds_path:
                        template_context.setdefault("dataset_path", ds_path)
                # staging steps and pre-run edits
                if dataset_profile.staging and dataset_profile.staging.steps:
                    template_context.setdefault("staging_steps", dataset_profile.staging.steps)
                if dataset_profile.pre_run_edits:
                    template_context.setdefault("pre_run_edits", dataset_profile.pre_run_edits)

            # --- 2. Validate Final Context ---
            missing_or_empty_params = []
            # We now require job_name as a standard parameter
            site_requirements = site_profile.job_requirements if site_profile else []
            system_requirements = self.system_config.get("job_requirements", [])
            required_params = list(dict.fromkeys(site_requirements + system_requirements + ["job_name"]))
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

                # The "tool" in a templated recipe is a generic command (e.g., 'submit'); resolve via scheduler KB
                submit_command = self._resolve_command(recipe["tool"]) 

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
            tool_name = self._resolve_command(recipe['tool'])
            
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
