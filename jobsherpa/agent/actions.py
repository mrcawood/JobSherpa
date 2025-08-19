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
from jobsherpa.agent.types import ActionResult
from jobsherpa.agent.recipe_index import SimpleKeywordIndex
from jobsherpa.kb.models import SystemProfile, ApplicationRecipe
from jobsherpa.kb.dataset_index import DatasetIndex
from jobsherpa.kb.module_client import ModuleClient
from jobsherpa.kb.system_index import SystemIndex
from jobsherpa.kb.app_registry import AppRegistry
from jobsherpa.kb.site_loader import load_site_profile
from jobsherpa.util.io import read_yaml
from jobsherpa.kb.service import KnowledgeBaseService
from jobsherpa.util.errors import ExceptionManager
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

class _ParamRegistry:
    """
    Minimal registry to track parameter origins for dry-run reporting.
    """
    def __init__(self) -> None:
        self._items: list[tuple[str, str, str]] = []  # (key, value, origin)

    def set(self, key: str, value, origin: str) -> None:
        try:
            val_str = "" if value is None else str(value)
        except Exception:
            val_str = str(value)
        # Overwrite if exists
        for i, (k, _, _) in enumerate(self._items):
            if k == key:
                self._items[i] = (key, val_str, origin)
                break
        else:
            self._items.append((key, val_str, origin))

    def setdefault(self, key: str, value, origin: str) -> None:
        if not any(k == key for (k, _, _) in self._items):
            self.set(key, value, origin)

    def render_table(self) -> str:
        if not self._items:
            return ""
        rows = sorted(self._items, key=lambda t: t[0])
        col1 = max(len("Parameter"), max(len(k) for k, _, _ in rows))
        col2 = max(len("Value"), max(len(v) for _, v, _ in rows))
        col3 = max(len("Origin"), max(len(o) for _, _, o in rows))
        header = f"{'Parameter'.ljust(col1)}  {'Value'.ljust(col2)}  {'Origin'.ljust(col3)}"
        sep = f"{'-'*col1}  {'-'*col2}  {'-'*col3}"
        lines = [header, sep]
        for k, v, o in rows:
            lines.append(f"{k.ljust(col1)}  {v.ljust(col2)}  {o.ljust(col3)}")
        return "\n".join(lines)

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
        # Private cache of scheduler command mappings; do not expose in system_config/template context
        self._scheduler_commands: dict[str, str] = {}

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
        # Populate private cache once
        if not self._scheduler_commands:
            if scheduler_name in DEFAULT_SCHEDULER_COMMANDS:
                self._scheduler_commands = DEFAULT_SCHEDULER_COMMANDS[scheduler_name]
            else:
                sched_profile = load_scheduler_profile(scheduler_name, base_dir=self.knowledge_base_dir)
                if sched_profile and getattr(sched_profile, "commands", None):
                    try:
                        self._scheduler_commands = sched_profile.commands.model_dump(exclude_none=True)  # type: ignore[attr-defined]
                    except AttributeError:
                        self._scheduler_commands = sched_profile.commands.dict(exclude_none=True)  # type: ignore[attr-defined]
                # Backward-compat fallback: do NOT write into system_config; only read if present
                if not self._scheduler_commands and isinstance(self.system_config, dict):
                    sc = self.system_config.get("commands")
                    if isinstance(sc, dict):
                        self._scheduler_commands = {k: v for k, v in sc.items() if isinstance(v, str)}
        commands_map = self._scheduler_commands or {}
        return commands_map.get(generic_command, generic_command)

    def run(self, prompt: str, context: Optional[dict] = None) -> ActionResult:
        # First, try to update the agent's configuration from the conversational context
        provenance = _ParamRegistry()
        kb_load_notes: list[str] = []
        kb_service = KnowledgeBaseService(base_dir=self.knowledge_base_dir)
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
                provenance.set("workspace", expanded_path, "user input")
                self.workspace_manager.base_path = Path(expanded_path)
                
            if 'system' in context and not self.system_config:
                system_name = context['system']
                system_config_path = os.path.join(self.knowledge_base_dir, "system", f"{system_name}.yaml")
                if os.path.exists(system_config_path):
                    logger.debug("Loading system profile from KB: %s", system_config_path)
                    self.system_config, self.system_profile_model = kb_service.load_system(system_name)
                    kb_load_notes.append(f"system KB: {system_config_path}")
                    # Reset scheduler command cache when system changes
                    self._scheduler_commands = {}
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
                    provenance.set("system", system_name, "user input")
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
                for k, v in self.system_config["defaults"].items():
                    provenance.setdefault(k, v, "system KB")
            if self.user_config:
                if isinstance(self.user_config, UserConfig):
                    defaults_obj = self.user_config.defaults
                    try:
                        defaults_dict = defaults_obj.model_dump(exclude_none=True)  # v2
                    except AttributeError:
                        defaults_dict = defaults_obj.dict(exclude_none=True)  # v1
                    default_context.update(defaults_dict)
                    for k, v in defaults_dict.items():
                        provenance.setdefault(k, v, "user KB")
                elif isinstance(self.user_config, dict) and "defaults" in self.user_config:
                    default_context.update(self.user_config["defaults"])
                    for k, v in self.user_config["defaults"].items():
                        provenance.setdefault(k, v, "user KB")
            
            # Merge defaults, allowing conversational context to override
            for key, value in default_context.items():
                template_context.setdefault(key, value)
            
            # Add recipe-specific args, which have the highest precedence
            template_context.update(recipe.get("template_args", {}))
            for k, v in recipe.get("template_args", {}).items():
                provenance.set(k, v, "recipe")

            # Integrate KB-derived fields with precedence: user KB > site KB > system KB > scheduler KB
            # System: module init, launcher, partition fallback
            if self.system_profile_model:
                # module init commands for environment setup
                if self.system_profile_model.module_init:
                    template_context.setdefault("module_init", self.system_profile_model.module_init)
                # launcher (e.g., ibrun/srun)
                # Site-level precedence: if a site is detected and has a launcher, prefer it
                site_profile = None
                try:
                    site_profile = kb_service.find_site_for_system(self.system_profile_model.name)
                except Exception:
                    site_profile = None

                if site_profile and getattr(site_profile, "launcher", None):
                    if "launcher" not in template_context:
                        template_context["launcher"] = site_profile.launcher
                        provenance.setdefault("launcher", site_profile.launcher, "site KB")
                elif getattr(self.system_profile_model, "commands", None) and getattr(self.system_profile_model.commands, "launcher", None):
                    if "launcher" not in template_context:
                        template_context["launcher"] = self.system_profile_model.commands.launcher
                        provenance.setdefault("launcher", self.system_profile_model.commands.launcher, "system KB")
                else:
                    # Scheduler KB launcher as last resort
                    launcher = (self._scheduler_commands or {}).get("launcher")
                    if launcher and "launcher" not in template_context:
                        template_context["launcher"] = launcher
                        provenance.setdefault("launcher", launcher, "scheduler KB")
                # partition fallback
                if not template_context.get("partition") and self.system_profile_model.available_partitions:
                    template_context["partition"] = self.system_profile_model.available_partitions[0]
                    provenance.set("partition", template_context["partition"], "system KB (fallback)")
                # reservation: optional in user/site/system defaults; pass-through if present
                if template_context.get("reservation"):
                    provenance.setdefault("reservation", template_context.get("reservation"), "user/system/site KB")

            # Application: module loads via ModuleClient abstraction
            if self.system_profile_model and recipe_model:
                mc = ModuleClient(system=self.system_profile_model, app=recipe_model)
                init_cmds = mc.module_init_commands()
                loads = mc.module_loads()
                if init_cmds:
                    template_context.setdefault("module_init", init_cmds)
                    provenance.setdefault("module_init", init_cmds, "app registry")
                if loads:
                    template_context.setdefault("module_loads", loads)
                    provenance.setdefault("module_loads", loads, "app registry")
                # Always honor system-bound exe_path if defined
                sys_bind = (self.system_profile_model.apps or {}).get(recipe_model.name, {})
                bound_exe = sys_bind.get("exe_path")
                if bound_exe:
                    template_context["wrf_exe"] = bound_exe
                    provenance.set("wrf_exe", bound_exe, "system KB app binding")
                # If not provided, resolve executable path via registry or binary name
                if "wrf_exe" not in template_context:
                    exe_name = (recipe_model.binary or {}).get("name") if recipe_model.binary else None
                    fallback_exe = self.app_registry.get_exe_path(self.system_profile_model.name, recipe_model.name)
                    if fallback_exe:
                        template_context["wrf_exe"] = fallback_exe
                        provenance.set("wrf_exe", fallback_exe, "app registry")
                    elif exe_name:
                        template_context["wrf_exe"] = exe_name
                        provenance.set("wrf_exe", exe_name, "binary name")

            # Dataset: resolve from user-provided context first, then fall back to scanning the prompt
            dataset_profile = None
            if context and isinstance(context, dict) and context.get("dataset"):
                dataset_profile = self.dataset_index.resolve(str(context.get("dataset")))
            if not dataset_profile:
                dataset_profile = self.dataset_index.resolve(prompt)
            if dataset_profile:
                hints = dataset_profile.resource_hints or {}
                if hints.get("nodes") is not None:
                    template_context.setdefault("nodes", hints.get("nodes"))
                    provenance.setdefault("nodes", hints.get("nodes"), "dataset KB")
                if hints.get("time") is not None:
                    template_context.setdefault("time", hints.get("time"))
                    provenance.setdefault("time", hints.get("time"), "dataset KB")
                # dataset path for the current system if available
                if self.system_profile_model and dataset_profile.locations:
                    sys_name = self.system_profile_model.name
                    ds_path = dataset_profile.locations.get(sys_name)
                    if not ds_path:
                        # Try case-insensitive match for system key
                        for key, value in dataset_profile.locations.items():
                            if str(key).lower() == str(sys_name).lower():
                                ds_path = value
                                break
                    if ds_path:
                        template_context.setdefault("dataset_path", ds_path)
                        provenance.setdefault("dataset_path", ds_path, "dataset KB")
                    else:
                        # Dataset selected but not available on this system
                        return ActionResult(
                            message=(
                                f"The dataset '{dataset_profile.name}' has no location defined for system '{self.system_profile_model.name}'. "
                                f"Please provide a dataset path or choose a different dataset."
                            ),
                            is_waiting=True,
                            param_needed="dataset_path",
                        )
                # staging steps and pre-run edits
                if dataset_profile.staging and dataset_profile.staging.steps:
                    # Pre-render staging steps to resolve nested Jinja placeholders (e.g., {{ staging.url }})
                    try:
                        ds_env = jinja2.Environment()
                        staging_url = getattr(dataset_profile.staging, "url", None)
                        rendered_steps = []
                        for step in (dataset_profile.staging.steps or []):
                            tmpl = ds_env.from_string(step)
                            rendered = tmpl.render(staging={"url": staging_url}, dataset_path=template_context.get("dataset_path"))
                            rendered_steps.append(rendered)
                        template_context.setdefault("staging_steps", rendered_steps)
                        # Validate unresolved placeholders
                        if any("{{" in s or "}}" in s for s in rendered_steps):
                            return ActionResult(
                                message=(
                                    "Some dataset staging steps contain unresolved placeholders. "
                                    "Please ensure dataset parameters (e.g., staging.url) are defined."
                                ),
                                is_waiting=True,
                                param_needed="dataset",
                            )
                    except Exception as e:
                        logger.error("Error rendering dataset staging steps: %s", e, exc_info=True)
                        return ActionResult(message=ExceptionManager.handle(e), error=str(e))
                if dataset_profile.pre_run_edits:
                    try:
                        ds_env = jinja2.Environment()
                        rendered_edits = []
                        for edit in (dataset_profile.pre_run_edits or []):
                            tmpl = ds_env.from_string(edit)
                            rendered = tmpl.render(dataset_path=template_context.get("dataset_path"))
                            rendered_edits.append(rendered)
                        template_context.setdefault("pre_run_edits", rendered_edits)
                        if any("{{" in s or "}}" in s for s in rendered_edits):
                            return ActionResult(
                                message=(
                                    "Some dataset pre-run edits contain unresolved placeholders. "
                                    "Please ensure dataset parameters are defined."
                                ),
                                is_waiting=True,
                                param_needed="dataset",
                            )
                    except Exception as e:
                        logger.error("Error rendering dataset pre-run edits: %s", e, exc_info=True)
                        return ActionResult(message=ExceptionManager.handle(e), error=str(e))
            else:
                # Enforce dataset presence if the application requires it
                if recipe_model and getattr(recipe_model, "dataset_required", False):
                    return ActionResult(
                        message=(
                            "This application requires a dataset. Please mention the dataset in your prompt "
                            "(e.g., 'new_conus12km') or provide dataset parameters."
                        ),
                        is_waiting=True,
                        param_needed="dataset",
                    )

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
                def _track(name: str, value):
                    logger.debug("Setting template param %-20s = %s", name, value)
                    return value

                env = jinja2.Environment(loader=jinja2.FileSystemLoader("tools"))
                # Add a simple debug function to trace substitutions if used in templates
                env.globals['dbg'] = _track
                template = env.get_template(recipe["template"])
                rendered_script = template.render(template_context)
                logger.debug("Rendered script content:\n%s", rendered_script)

                # Write the rendered script to a file in the isolated job directory
                with open(job_workspace.script_path, 'w') as f:
                    f.write(rendered_script)
                logger.info("Wrote rendered script to: %s", job_workspace.script_path)

                # The "tool" in a templated recipe is a generic command (e.g., 'submit'); resolve via scheduler KB
                submit_command = self._resolve_command(recipe["tool"])
                provenance.set("submit_command", submit_command, "scheduler KB" if submit_command != recipe["tool"] else "recipe")

                # The ToolExecutor will now execute from within the job directory
                execution_result = self.tool_executor.execute(
                    submit_command, 
                    [job_workspace.script_path.name], 
                    workspace=str(job_workspace.job_dir)
                )

            except jinja2.TemplateNotFound as e:
                logger.error("Template '%s' not found in tools directory.", recipe["template"])
                return ActionResult(message=ExceptionManager.handle(e), error=str(e))
            except Exception as e:
                logger.error("Error rendering template: %s", e, exc_info=True)
                return ActionResult(message=ExceptionManager.handle(e), error=str(e))
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
        if isinstance(execution_result, str) and execution_result.startswith("DRY-RUN:"):
            kb_lines = ("\n" + "\n".join(f"Loaded {note}" for note in kb_load_notes)) if kb_load_notes else ""
            table = provenance.render_table()
            if table or kb_lines:
                # Reorder for readability: show KB loads and parameter table before the execution line
                parts = [f"Found recipe '{recipe['name']}'."]
                if kb_lines:
                    parts.append(kb_lines.strip())
                if table:
                    parts.append("\n".join(["Parameters and origin:", table]))
                parts.append(f"Execution result: {execution_result}")
                response = "\n\n".join(parts)
        
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
