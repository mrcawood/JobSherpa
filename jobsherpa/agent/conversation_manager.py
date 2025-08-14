from jobsherpa.agent.intent_classifier import IntentClassifier
from jobsherpa.agent.actions import RunJobAction, QueryHistoryAction

class ConversationManager:
    def __init__(
        self,
        intent_classifier: IntentClassifier,
        run_job_action: RunJobAction,
        query_history_action: QueryHistoryAction,
    ):
        self.intent_classifier = intent_classifier
        self.action_handlers = {
            "run_job": run_job_action,
            "query_history": query_history_action,
        }

    def handle_prompt(self, prompt: str):
        intent = self.intent_classifier.classify(prompt)
        
        handler = self.action_handlers.get(intent)
        
        if handler:
            return handler.run(prompt)
        else:
            # Handle unknown intent
            return "Sorry, I'm not sure how to handle that."
