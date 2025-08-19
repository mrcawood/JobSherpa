from jobsherpa.agent.intent_classifier import IntentClassifier
from jobsherpa.agent.actions import RunJobAction, QueryHistoryAction
from jobsherpa.agent.config_manager import ConfigManager
from jobsherpa.agent.types import ActionResult
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class ConversationManager:
    """
    Orchestrates the conversation flow, determining user intent and delegating
    to the appropriate action handlers. Manages conversational context.
    """
    def __init__(self, intent_classifier, run_job_action, query_history_action, user_profile_path: Optional[str] = None):
        self.intent_classifier = intent_classifier
        self.run_job_action = run_job_action
        self.query_history_action = query_history_action
        self.user_profile_path = user_profile_path
        
        # State for multi-turn conversations
        self._is_waiting = False
        self._pending_action = None
        self._pending_prompt = None
        self._context = {}
        self._param_needed = None
        self._is_waiting_for_save_confirmation = False

    def is_waiting_for_input(self) -> bool:
        """Returns True if the manager is waiting for a follow-up response."""
        return self._is_waiting
        
    def handle_prompt(self, prompt: str):
        logger.debug("Handling prompt: %s", prompt)
        # State 1: Waiting for save confirmation/selection
        if self._is_waiting_for_save_confirmation:
            logger.debug("Waiting for save confirmation. User replied: %s", prompt)
            reply = (prompt or "").strip().lower()
            # Normalize reply into a selection of keys
            keys_to_save = None  # None => save nothing
            if reply in {"y", "yes", "all"}:
                keys_to_save = list(self._context.keys())
            elif reply in {"n", "no", "none"}:
                keys_to_save = []
            else:
                # Parse comma/space separated keys
                parts = [p.strip() for p in reply.replace(" ", ",").split(",") if p.strip()]
                if parts:
                    known = set(self._context.keys())
                    keys_to_save = [k for k in parts if k in known]
                    unknown = [k for k in parts if k not in known]
                    if unknown:
                        logger.warning("Ignoring unknown keys in save selection: %s", ", ".join(unknown))
                else:
                    keys_to_save = []

            if keys_to_save is not None:
                if keys_to_save:
                    self._save_context_to_profile(selected_keys=keys_to_save)
                    response = "Configuration saved!"
                else:
                    response = "Okay, I won't save these settings."
            else:
                response = "Okay, I won't save these settings."
            self._reset_conversation_state()
            return response, None, False

        # State 2: Waiting for a missing parameter
        if self._is_waiting and self._pending_action and self._param_needed:
            logger.debug("Received value for missing param '%s': %s", self._param_needed, prompt)
            self._context[self._param_needed] = prompt.strip()
            # Re-run the pending action with the new context
            result: ActionResult = self._pending_action.run(
                prompt=self._pending_prompt, context=self._context
            )

            if not result.is_waiting:  # Job was submitted, failed, or dry-run finished
                self._is_waiting = False
                # Offer to save only if we have a profile path to save to
                response = result.message
                job_id = result.job_id
                if self._context and self.user_profile_path:
                    response += (
                        f"\nWould you like to save {self._context} to your profile? "
                        f"(reply 'all', 'none', or comma-separated keys like allocation,partition)"
                    )
                    self._is_waiting_for_save_confirmation = True
                    self._is_waiting = True  # Keep session open for the save confirmation
                    logger.debug("Awaiting save confirmation for context: %s", self._context)
                else:
                    self._reset_conversation_state()
            else:  # Still waiting for more params
                self._param_needed = result.param_needed
                logger.debug("Still missing parameter: %s", self._param_needed)
                # Provide the latest message to the user while waiting
                response = result.message
                job_id = result.job_id

            return response, job_id, self._is_waiting

        # State 3: New conversation
        intent = self.intent_classifier.classify(prompt)
        logger.debug("Classified intent: %s", intent)
        if intent == "query_history":
            logger.debug("Dispatching to QueryHistoryAction")
            response = self.query_history_action.run(prompt=prompt)
            return response, None, False
        else:
            # Default to running a job for any non-query intent
            logger.debug("Dispatching to RunJobAction")
            result: ActionResult = self.run_job_action.run(prompt=prompt, context={})
            response = result.message
            job_id = result.job_id
            is_waiting = result.is_waiting
            if is_waiting:
                self._is_waiting = True
                self._pending_action = self.run_job_action
                self._pending_prompt = prompt
                self._param_needed = result.param_needed
                logger.debug("Waiting for parameter: %s", self._param_needed)
            return response, job_id, is_waiting

    def _save_context_to_profile(self, selected_keys: Optional[list[str]] = None):
        """Loads the user profile, updates it with the context (optionally restricted to selected_keys), and saves it.

        Fault-tolerant: if the existing profile fails validation, we create a minimal
        profile and still persist the selected keys rather than crashing.
        """
        if not self.user_profile_path:
            return  # Should not happen in this flow

        config_manager = ConfigManager(config_path=self.user_profile_path)
        try:
            config = config_manager.load()
        except Exception as e:
            # Build a minimal config and proceed
            logger.warning("Profile load failed at %s (%s). Creating minimal config to persist selected keys.", self.user_profile_path, e)
            try:
                from jobsherpa.config import UserConfig, UserConfigDefaults
                config = UserConfig(defaults=UserConfigDefaults(workspace="", system=""))
            except Exception:
                # Last resort: do nothing
                logger.error("Failed to construct minimal user config; aborting save.")
                return

        items = list(self._context.items())
        if selected_keys is not None:
            selected = set(selected_keys)
            items = [(k, v) for k, v in items if k in selected]
        for key, value in items:
            try:
                # Expand env vars and user in workspace before saving
                if key == "workspace" and isinstance(value, str):
                    import os
                    value = os.path.expandvars(os.path.expanduser(value))
                setattr(config.defaults, key, value)
            except Exception:
                logger.warning("Skipping unsupported key '%s' during save.", key)

        try:
            config_manager.save(config)
            logger.info("Saved context to profile %s: %s", self.user_profile_path, dict(items))
        except Exception as e:
            logger.error("Failed to save profile at %s (%s)", self.user_profile_path, e)
        
    def _reset_conversation_state(self):
        """Resets all state attributes of the conversation."""
        self._is_waiting = False
        self._pending_action = None
        self._pending_prompt = None
        self._context = {}
        self._param_needed = None
        self._is_waiting_for_save_confirmation = False
