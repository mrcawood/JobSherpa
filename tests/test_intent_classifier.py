import pytest

from jobsherpa.agent.intent_classifier import IntentClassifier

@pytest.fixture
def classifier():
    return IntentClassifier()

def test_classify_run_job_intent(classifier):
    """
    Tests that prompts related to starting a new job are correctly
    classified as the 'run_job' intent.
    """
    prompts = [
        "Run the hello world job",
        "Generate a random number for me",
        "Can you submit my WRF simulation?",
        "start the test",
    ]
    for prompt in prompts:
        intent = classifier.classify(prompt)
        assert intent == "run_job"

def test_classify_query_history_intent(classifier):
    """
    Tests that prompts asking about previous jobs are correctly
    classified as the 'query_history' intent.
    """
    prompts = [
        "What was the result of my last job?",
        "Tell me about job 12345",
        "what was the status of my most recent run",
        "get the result of the random number job",
    ]
    for prompt in prompts:
        intent = classifier.classify(prompt)
        assert intent == "query_history"

def test_classify_unknown_intent(classifier):
    """
    Tests that prompts that don't match any known keywords default
    to 'unknown'.
    """
    prompt = "What is the weather like today?"
    intent = classifier.classify(prompt)
    assert intent == "unknown"
