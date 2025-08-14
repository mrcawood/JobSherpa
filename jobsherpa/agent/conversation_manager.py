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
        if self._is_waiting and self._pending_action:
            # --- We are in a multi-turn conversation ---
            # Parse the user's response to get the missing parameters
            new_context = self._parse_user_response(prompt)
            self._context.update(new_context)
            
            # Re-run the pending action with the updated context
            response, job_id = self._pending_action.run(
                prompt=self._pending_prompt, context=self._context
            )
            
            # Reset the state if the action is now complete
            if job_id is not None:
                self._is_waiting = False
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
                response, job_id = handler.run(prompt=prompt, context={})
                # If the handler asks a question (no job ID returned), set the state
                if job_id is None:
                    self._is_waiting = True
                    self._pending_action = handler
                    self._pending_prompt = prompt
                return response, job_id, self._is_waiting
            else: # It's a query action
                response = handler.run(prompt=prompt)
                return response, None, False # No job ID for queries, not waiting
        else:
            return "Sorry, I'm not sure how to handle that.", None, False
