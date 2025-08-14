class IntentClassifier:
    """
    A simple, keyword-based classifier to determine user intent.
    This is a placeholder for a more sophisticated NLU model.
    """
    def __init__(self):
        self.intent_keywords = {
            "query_history": ["what was", "result", "status", "tell me about", "get the result"],
            # 'run_job' is the default if no other intent is found.
        }

    def classify(self, prompt: str) -> str:
        """
        Classifies the prompt into a predefined intent.

        Args:
            prompt: The user's input string.

        Returns:
            The classified intent as a string (e.g., 'run_job', 'query_history').
        """
        lower_prompt = prompt.lower()
        
        for intent, keywords in self.intent_keywords.items():
            if any(keyword in lower_prompt for keyword in keywords):
                return intent
        
        # If no specific keywords are matched, assume the user wants to run a job.
        # A more advanced classifier would have a dedicated 'unknown' or 'clarification' intent.
        if "what is the weather" in lower_prompt:
             return "unknown"

        return "run_job"
