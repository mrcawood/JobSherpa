import yaml
import os
import re
import jinja2
import logging
import uuid
from typing import Optional
from jobsherpa.agent.tool_executor import ToolExecutor
from jobsherpa.agent.job_state_tracker import JobStateTracker
from haystack.document_stores import InMemoryDocumentStore
from haystack.nodes import BM25Retriever
from haystack import Pipeline
from haystack import Document

logger = logging.getLogger(__name__)

class JobSherpaAgent:
    """
    The core logic of the JobSherpa AI agent.
    This class is UI-agnostic and exposes a clean API.
    """
    def __init__(
        self, 
        dry_run: bool = False, 
        knowledge_base_dir: str = "knowledge_base",
        system_profile: Optional[str] = None,
        user_profile: Optional[str] = None,
        user_config: Optional[dict] = None # For testing
    ):
        """
        Initializes the agent.
        """
        self.dry_run = dry_run
        self.tool_executor = ToolExecutor(dry_run=self.dry_run)
        self.knowledge_base_dir = knowledge_base_dir
        
        self.user_config = user_config or self._load_user_config(user_profile)
        self.workspace = self.user_config.get("defaults", {}).get("workspace") if self.user_config else None

        # Determine the system profile to use
        effective_system_profile = system_profile
        if not effective_system_profile:
            if self.user_config:
                effective_system_profile = self.user_config.get("defaults", {}).get("system")
            
            if not effective_system_profile:
                raise ValueError(
                    "User profile must contain a 'system' key in the 'defaults' section. "
                    "You can set it by running: jobsherpa config set system <system_name>"
                )
        
        self.system_config = self._load_system_config(effective_system_profile)
        self.tracker = JobStateTracker()
        self.rag_pipeline = self._initialize_rag_pipeline()
        logger.info("JobSherpaAgent initialized for system: %s", effective_system_profile)

    def start(self):
        """Starts the agent's background threads."""
        self.tracker.start_monitoring()
        logger.info("Agent background monitoring started.")

    def check_jobs(self):
        """Triggers the job state tracker to check for updates."""
        self.tracker.check_and_update_statuses()

    def stop(self):
        """Stops the agent's background threads."""
        self.tracker.stop_monitoring()
        logger.info("Agent background monitoring stopped.")

    def get_job_status(self, job_id: str) -> Optional[str]:
        """Gets the status of a job from the tracker."""
        return self.tracker.get_status(job_id)

    def _load_app_recipes(self):
        """Loads all application recipes from the knowledge base."""
        recipes = {}
        app_dir = os.path.join(self.knowledge_base_dir, "applications")
        if not os.path.isdir(app_dir):
            logger.warning("Applications directory not found at: %s", app_dir)
            return {}
        for filename in os.listdir(app_dir):
            if filename.endswith(".yaml"):
                with open(os.path.join(app_dir, filename), 'r') as f:
                    recipe = yaml.safe_load(f)
                    recipes[recipe['name']] = recipe
        return recipes

    def _load_system_config(self, profile_name: Optional[str]):
        """Loads a specific system configuration from the knowledge base."""
        if not profile_name:
            return None
        
        system_file = os.path.join(self.knowledge_base_dir, "system", f"{profile_name}.yaml")
        logger.debug("Loading system profile from: %s", system_file)
        if os.path.exists(system_file):
            with open(system_file, 'r') as f:
                return yaml.safe_load(f)
        return None

    def _load_user_config(self, profile_name: Optional[str]):
        """Loads a specific user configuration from the knowledge base."""
        if not profile_name:
            return None
        
        user_file = os.path.join(self.knowledge_base_dir, "user", f"{profile_name}.yaml")
        logger.debug("Loading user profile from: %s", user_file)
        if os.path.exists(user_file):
            with open(user_file, 'r') as f:
                return yaml.safe_load(f)
        return None

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

        # Check if the recipe uses a template
        if "template" in recipe:
            template_name = recipe["template"]
            
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

            logger.info("Rendering script from template: %s", template_name)
            
            # Ensure workspace is defined for templated jobs
            if not self.workspace:
                error_msg = (
                    "Workspace must be defined in user profile for templated jobs.\n"
                    "You can set it by running: jobsherpa config set workspace /path/to/your/workspace"
                )
                logger.error(error_msg)
                return error_msg, None

            # Create a Jinja2 environment
            template_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'tools')
            env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
            
            try:
                template = env.get_template(template_name)
                rendered_script = template.render(context)
                logger.debug("Rendered script content:\n%s", rendered_script)

                # Write the rendered script to a file in the workspace
                scripts_dir = os.path.join(self.workspace, ".jobsherpa", "scripts")
                os.makedirs(scripts_dir, exist_ok=True)
                script_filename = f"job-{uuid.uuid4()}.sh"
                script_path = os.path.join(scripts_dir, script_filename)
                with open(script_path, 'w') as f:
                    f.write(rendered_script)
                logger.info("Wrote rendered script to: %s", script_path)

                # The "tool" in a templated recipe is the command to execute the script
                submit_command = recipe["tool"]
                if self.system_config and submit_command in self.system_config.get("commands", {}):
                    submit_command = self.system_config["commands"][submit_command]

                # The ToolExecutor will now receive the script path as an argument
                execution_result = self.tool_executor.execute(submit_command, [script_path], workspace=self.workspace)

            except jinja2.TemplateNotFound:
                logger.error("Template '%s' not found in tools directory.", template_name)
                return f"Error: Template '{template_name}' not found.", None
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
            execution_result = self.tool_executor.execute(tool_name, args, workspace=self.workspace)

        job_id = self._parse_job_id(execution_result)
        if job_id:
            # Pass the parser info to the tracker when registering the job
            output_parser = recipe.get("output_parser")
            self.tracker.register_job(job_id, output_parser_info=output_parser)
            logger.info("Job %s submitted successfully.", job_id)
            response = f"Found recipe '{recipe['name']}'.\nJob submitted successfully with ID: {job_id}"
            return response, job_id

        logger.info("Execution finished, but no job ID was parsed.")
        response = f"Found recipe '{recipe['name']}'.\nExecution result: {execution_result}"
        return response, None

    def get_job_result(self, job_id: str) -> Optional[str]:
        """Gets the parsed result of a completed job."""
        return self.tracker.get_result(job_id)
