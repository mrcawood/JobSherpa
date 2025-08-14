import yaml
import os
import re
import jinja2
import logging
import uuid
from typing import Optional
from jobsherpa.agent.tool_executor import ToolExecutor
from jobsherpa.agent.job_history import JobHistory
from jobsherpa.agent.workspace_manager import WorkspaceManager
from jobsherpa.agent.intent_classifier import IntentClassifier
from jobsherpa.agent.conversation_manager import ConversationManager
from jobsherpa.agent.actions import RunJobAction, QueryHistoryAction
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
        Initializes the agent and all its components.
        """
        # --- 1. Load Core Configs ---
        self.user_config = user_config or self._load_user_config(user_profile, knowledge_base_dir)
        
        if not self.user_config or "defaults" not in self.user_config:
            raise ValueError("User profile is missing 'defaults' section.")

        self.workspace = self.user_config.get("defaults", {}).get("workspace")
        if not self.workspace:
             raise ValueError(
                "User profile must contain a 'workspace' key in the 'defaults' section. "
                "You can set it by running: jobsherpa config set workspace <path>"
            )
        
        history_dir = os.path.join(self.workspace, ".jobsherpa")
        os.makedirs(history_dir, exist_ok=True)
        history_file = os.path.join(history_dir, "history.json")
        
        effective_system_profile = system_profile
        if not effective_system_profile:
            if self.user_config:
                effective_system_profile = self.user_config.get("defaults", {}).get("system")
            if not effective_system_profile:
                raise ValueError(
                    "User profile must contain a 'system' key in the 'defaults' section. "
                    "You can set it by running: jobsherpa config set system <system_name>"
                )
        
        system_config = self._load_system_config(effective_system_profile, knowledge_base_dir)

        # --- 2. Initialize Components ---
        tool_executor = ToolExecutor(dry_run=dry_run)
        job_history = JobHistory(history_file_path=history_file)
        workspace_manager = WorkspaceManager(base_path=self.workspace)
        intent_classifier = IntentClassifier()
        
        # --- 3. Initialize Action Handlers (passing dependencies) ---
        run_job_action = RunJobAction(
            job_history=job_history,
            workspace_manager=workspace_manager,
            tool_executor=tool_executor,
            knowledge_base_dir=knowledge_base_dir,
            user_config=self.user_config,
            system_config=system_config,
        )
        query_history_action = QueryHistoryAction(job_history=job_history)

        # --- 4. Initialize the Conversation Manager ---
        self.conversation_manager = ConversationManager(
            intent_classifier=intent_classifier,
            run_job_action=run_job_action,
            query_history_action=query_history_action,
        )

        logger.info("JobSherpaAgent initialized.")

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

    def _load_system_config(self, profile_name: Optional[str], knowledge_base_dir: str):
        """Loads a specific system configuration from the knowledge base."""
        if not profile_name:
            return None
        
        system_file = os.path.join(knowledge_base_dir, "system", f"{profile_name}.yaml")
        logger.debug("Loading system profile from: %s", system_file)
        if os.path.exists(system_file):
            with open(system_file, 'r') as f:
                return yaml.safe_load(f)
        return None

    def _load_user_config(self, profile_name: Optional[str], knowledge_base_dir: str):
        """Loads a specific user configuration from the knowledge base."""
        # This will be refactored later
        if not profile_name:
            return None
        
        user_file = os.path.join(knowledge_base_dir, "user", f"{profile_name}.yaml")
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

    def run(self, prompt: str):
        """
        The main entry point for the agent. Delegates handling to the ConversationManager.
        """
        logger.info("Agent received prompt: '%s'", prompt)
        return self.conversation_manager.handle_prompt(prompt)

    def get_job_result(self, job_id: str) -> Optional[str]:
        """Gets the parsed result of a completed job."""
        return self.tracker.get_result(job_id)
