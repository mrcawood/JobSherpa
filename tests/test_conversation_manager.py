import pytest
from unittest.mock import MagicMock

from jobsherpa.agent.conversation_manager import ConversationManager

def test_conversation_manager_routes_to_run_job_action():
    """
    Tests that a 'run_job' intent correctly calls the RunJobAction handler.
    """
    # 1. Setup Mocks
    mock_classifier = MagicMock()
    mock_run_job_action = MagicMock()
    mock_query_history_action = MagicMock()
    
    mock_classifier.classify.return_value = "run_job"
    mock_run_job_action.run.return_value = ("Success", "12345", False, None) # Ensure it returns a tuple
    
    # 2. Initialize Manager with Mocks
    manager = ConversationManager(
        intent_classifier=mock_classifier,
        run_job_action=mock_run_job_action,
        query_history_action=mock_query_history_action
    )
    
    # 3. Act
    prompt = "Run a job"
    manager.handle_prompt(prompt)
    
    # 4. Assert
    mock_classifier.classify.assert_called_with(prompt)
    mock_run_job_action.run.assert_called_with(prompt=prompt, context={})
    mock_query_history_action.run.assert_not_called()

def test_conversation_manager_routes_to_query_history_action():
    """
    Tests that a 'query_history' intent correctly calls the QueryHistoryAction handler.
    """
    # 1. Setup Mocks
    mock_classifier = MagicMock()
    mock_run_job_action = MagicMock()
    mock_query_history_action = MagicMock()
    
    mock_classifier.classify.return_value = "query_history"
    
    # 2. Initialize Manager with Mocks
    manager = ConversationManager(
        intent_classifier=mock_classifier,
        run_job_action=mock_run_job_action,
        query_history_action=mock_query_history_action
    )
    
    # 3. Act
    prompt = "What was my last job?"
    manager.handle_prompt(prompt)
    
    # 4. Assert
    mock_classifier.classify.assert_called_with(prompt)
    mock_run_job_action.run.assert_not_called()
    mock_query_history_action.run.assert_called_with(prompt=prompt)

def test_conversation_manager_handles_multi_turn_conversation():
    """
    Tests that the ConversationManager can handle a multi-turn conversation
    where the user provides a missing parameter in a second turn.
    """
    # 1. Setup
    mock_intent_classifier = MagicMock()
    mock_run_job_action = MagicMock()
    mock_query_history_action = MagicMock()
    
    manager = ConversationManager(
        intent_classifier=mock_intent_classifier,
        run_job_action=mock_run_job_action,
        query_history_action=mock_query_history_action,
    )
    
    # --- Turn 1: User asks to run a job, but a parameter is missing ---
    mock_intent_classifier.classify.return_value = "run_job"
    # Simulate RunJobAction asking for a missing parameter
    mock_run_job_action.run.return_value = (
        "I need an allocation. What allocation should I use?", None, True, "allocation"
    )
    
    response, _ = manager.handle_prompt("Run my job")
    
    # Assert that the manager asked the question and is now waiting for a response
    assert "I need an allocation" in response
    assert manager.is_waiting_for_input()
    
    # --- Turn 2: User provides the missing allocation ---
    # The intent should not be re-classified; the manager should use the context
    mock_intent_classifier.reset_mock()
    # Simulate RunJobAction now succeeding with the new context
    mock_run_job_action.run.return_value = (
        "Job submitted with ID: 12345", "12345", False, None
    )
    
    response, _ = manager.handle_prompt("use allocation abc-123")
    
    # Assert that the manager used the new context and submitted the job
    mock_intent_classifier.classify.assert_not_called()
    mock_run_job_action.run.assert_called_with(
        prompt="Run my job",
        context={"allocation": "abc-123"}
    )
    assert "Job submitted with ID: 12345" in response
    assert not manager.is_waiting_for_input()
