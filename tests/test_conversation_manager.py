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
    mock_run_job_action.run.assert_called_with(prompt)
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
    mock_query_history_action.run.assert_called_with(prompt)
