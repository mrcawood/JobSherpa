from jobsherpa.agent.intent_classifier import IntentClassifier
from jobsherpa.agent.actions import RunJobAction, QueryHistoryAction

class ConversationManager:
    """
    Orchestrates the conversation flow, determining user intent and delegating
    to the appropriate action handlers. Manages conversational context.
    """
    def __init__(self, intent_classifier, run_job_action, query_history_action):
        self.intent_classifier = intent_classifier
        self.run_job_action = run_job_action
        self.query_history_action = query_history_action
        
        # State for multi-turn conversations
        self._is_waiting = False
        self._pending_action = None
        self._pending_prompt = None
        self._context = {}
        self._param_needed = None # The specific parameter we are asking for

    def is_waiting_for_input(self) -> bool:
        """Returns True if the manager is waiting for a follow-up response."""
        return self._is_waiting

    def _parse_user_response(self, response: str) -> dict:
        """A simple parser to extract key-value pairs from a user's response."""
        # This is a very basic implementation. A more robust solution would
        # use a proper NLP entity extraction model.
        parts = response.lower().split()
        context = {}
        if "allocation" in parts:
            try:
                # Find the value after the keyword "allocation"
                idx = parts.index("allocation") + 1
                if idx < len(parts):
                    context["allocation"] = parts[idx]
            except (ValueError, IndexError):
                pass
        return context

    def handle_prompt(self, prompt: str):
        if self._is_waiting and self._pending_action and self._param_needed:
            # --- We are in a multi-turn conversation ---
            # Assume the user's entire response is the value for the needed parameter
            self._context[self._param_needed] = prompt.strip()
            
            # Re-run the pending action with the updated context
            response, job_id, is_waiting, param_needed = self._pending_action.run(
                prompt=self._pending_prompt, context=self._context
            )
            
            self._is_waiting = is_waiting
            self._param_needed = param_needed

            if not self._is_waiting:
                # If the action is now complete, reset the state
                self._pending_action = None
                self._pending_prompt = None
                self._context = {}
                
            return response, job_id, self._is_waiting

        # --- This is a new conversation ---
        intent = self.intent_classifier.classify(prompt)
        handler = None
        if intent == "run_job":
            handler = self.run_job_action
        elif intent == "query_history":
            handler = self.query_history_action

        if handler:
            if intent == "run_job":
                response, job_id, is_waiting, param_needed = handler.run(prompt=prompt, context={})
                # If the handler asks a question, set the state
                if is_waiting:
                    self._is_waiting = True
                    self._pending_action = handler
                    self._pending_prompt = prompt
                    self._param_needed = param_needed
                return response, job_id, self._is_waiting
            else: # It's a query action
                response = handler.run(prompt=prompt)
                return response, None, False # No job ID for queries, not waiting
        else:
            return "Sorry, I'm not sure how to handle that.", None, False
