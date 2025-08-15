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
        # State 1: Waiting for save confirmation
        if self._is_waiting_for_save_confirmation:
            logger.debug("Waiting for save confirmation. User replied: %s", prompt)
            if prompt.lower() in ["y", "yes"]:
                self._save_context_to_profile()
                response = "Configuration saved!"
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

            if not result.is_waiting:  # Job was submitted or failed
                self._is_waiting = False
                # Offer to save only if we have a profile path to save to
                response = result.message
                job_id = result.job_id
                if job_id and self._context and self.user_profile_path:
                    response += f"\nWould you like to save {self._context} to your profile? [y/N]"
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

    def _save_context_to_profile(self):
        """Loads the user profile, updates it with the context, and saves it."""
        if not self.user_profile_path:
            return # Should not happen in this flow
            
        config_manager = ConfigManager(config_path=self.user_profile_path)
        config = config_manager.load()
        
        for key, value in self._context.items():
            setattr(config.defaults, key, value)
            
        config_manager.save(config)
        logger.info("Saved context to profile %s: %s", self.user_profile_path, self._context)
        
    def _reset_conversation_state(self):
        """Resets all state attributes of the conversation."""
        self._is_waiting = False
        self._pending_action = None
        self._pending_prompt = None
        self._context = {}
        self._param_needed = None
        self._is_waiting_for_save_confirmation = False
