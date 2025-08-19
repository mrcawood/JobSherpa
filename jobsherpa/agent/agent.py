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
from jobsherpa.agent.config_manager import ConfigManager
from jobsherpa.config import UserConfig
from jobsherpa.util.io import read_yaml
from jobsherpa.kb.service import KnowledgeBaseService

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
        # The user_config dict is now replaced by a UserConfig object for testing
        user_config_override: Optional[UserConfig] = None,
    ):
        """Initializes the agent and all its components."""
        # --- 1. Load Core Configs ---
        profile_path = None # Ensure profile_path is always defined
        if user_config_override:
            user_config = user_config_override
            profile_path = None # No path when overriding
        else:
            profile_path = os.path.join(knowledge_base_dir, "user", f"{user_profile}.yaml")
            if not os.path.exists(profile_path):
                from jobsherpa.config import UserConfig, UserConfigDefaults
                logger.warning(f"User profile not found at {profile_path}. Starting with empty configuration.")
                # Create a new, empty config. The agent will ask for required values.
                user_config = UserConfig(defaults=UserConfigDefaults(workspace="", system=""))
                profile_path = None # No path, so don't offer to save later
            else:
                # Attempt to load; if invalid or missing required fields, fall back gracefully but salvage known defaults
                try:
                    user_config_manager = ConfigManager(config_path=profile_path)
                    user_config = user_config_manager.load()
                except Exception as e:
                    from jobsherpa.config import UserConfig, UserConfigDefaults
                    logger.warning("Failed to load user profile at %s (%s). Attempting lenient load.", profile_path, e)
                    # Lenient loader: keep known defaults, warn on unknown keys, prompt later for missing requireds
                    try:
                        with open(profile_path, "r") as f:
                            raw = yaml.safe_load(f) or {}
                    except Exception:
                        raw = {}
                    defaults_raw = raw.get("defaults", {}) if isinstance(raw, dict) else {}
                    known_keys = {"workspace", "system", "partition", "allocation"}
                    unknown_keys = [k for k in defaults_raw.keys() if k not in known_keys]
                    if unknown_keys:
                        logger.warning(
                            "User profile %s contains unknown default keys: %s",
                            profile_path,
                            ", ".join(sorted(unknown_keys)),
                        )
                    workspace = defaults_raw.get("workspace", "")
                    system = defaults_raw.get("system", "")
                    partition = defaults_raw.get("partition")
                    allocation = defaults_raw.get("allocation")
                    user_config = UserConfig(
                        defaults=UserConfigDefaults(
                            workspace=workspace,
                            system=system,
                            partition=partition,
                            allocation=allocation,
                        )
                    )
                    # Keep profile_path so we can offer to save later into the same file
        
        self.workspace = user_config.defaults.workspace
        history_dir = os.path.join(self.workspace, ".jobsherpa") if self.workspace else os.path.join(os.getcwd(), ".jobsherpa")
        os.makedirs(history_dir, exist_ok=True)
        history_file = os.path.join(history_dir, "history.json")
        
        effective_system_profile = system_profile or user_config.defaults.system
        kb_service = KnowledgeBaseService(base_dir=knowledge_base_dir)
        
        system_config = None
        if effective_system_profile:
            system_config, _ = kb_service.load_system(effective_system_profile)

        # --- 2. Initialize Components ---
        tool_executor = ToolExecutor(dry_run=dry_run)
        job_history = JobHistory(history_file_path=history_file)
        workspace_manager = WorkspaceManager(base_path=self.workspace)
        intent_classifier = IntentClassifier()
        
        # --- 3. Initialize Action Handlers (passing the typed config object) ---
        run_job_action = RunJobAction(
            job_history=job_history,
            workspace_manager=workspace_manager,
            tool_executor=tool_executor,
            knowledge_base_dir=knowledge_base_dir,
            user_config=user_config,
            system_config=system_config,
        )
        query_history_action = QueryHistoryAction(job_history=job_history)

        # --- 4. Initialize Conversation Manager ---
        self.conversation_manager = ConversationManager(
            intent_classifier=intent_classifier,
            run_job_action=run_job_action,
            query_history_action=query_history_action,
            user_profile_path=profile_path,
        )

        logger.info("JobSherpaAgent initialized.")

    def run(self, prompt: str) -> tuple[str, Optional[str], bool]:
        """
        Runs a single turn of the conversation.
        Returns the agent's response, an optional job ID, and a boolean
        indicating if the agent is waiting for more input.
        """
        response, job_id, is_waiting = self.conversation_manager.handle_prompt(prompt)
        return response, job_id, is_waiting

    # Deprecated helper methods and dead code below will be removed as part of refactor

    
