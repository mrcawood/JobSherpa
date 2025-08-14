import pytest
from unittest.mock import patch, MagicMock
from jobsherpa.agent.agent import JobSherpaAgent

@patch("jobsherpa.agent.agent.ConversationManager")
@patch("jobsherpa.agent.agent.JobHistory")
@patch("jobsherpa.agent.agent.WorkspaceManager")
@patch("jobsherpa.agent.agent.IntentClassifier")
@patch("jobsherpa.agent.agent.RunJobAction")
@patch("jobsherpa.agent.agent.QueryHistoryAction")
@patch.object(JobSherpaAgent, "_load_user_config")
def test_agent_initialization_wires_components_correctly(
    mock_load_config, mock_query_action, mock_run_action,
    mock_classifier, mock_workspace_manager, mock_history, mock_conversation_manager
):
    """
    Tests that the agent's __init__ method correctly instantiates and
    wires together all the components of the new architecture.
    """
    # 1. Setup
    mock_load_config.return_value = {"defaults": {"workspace": "/tmp", "system": "test"}}
    
    # 2. Act
    agent = JobSherpaAgent()
    
    # 3. Assert component initialization
    mock_history.assert_called_with(history_file_path="/tmp/.jobsherpa/history.json")
    mock_workspace_manager.assert_called_with(base_path="/tmp")
    mock_classifier.assert_called_once()
    
    # 4. Assert action handler initialization (with dependencies)
    mock_run_action.assert_called_with(
        job_history=mock_history.return_value,
        workspace_manager=mock_workspace_manager.return_value
    )
    mock_query_action.assert_called_with(job_history=mock_history.return_value)
    
    # 5. Assert conversation manager initialization
    mock_conversation_manager.assert_called_with(
        intent_classifier=mock_classifier.return_value,
        run_job_action=mock_run_action.return_value,
        query_history_action=mock_query_action.return_value
    )

@patch("jobsherpa.agent.agent.ConversationManager")
@patch.object(JobSherpaAgent, "_load_user_config", return_value={"defaults": {"workspace": "/tmp", "system": "test"}})
def test_agent_run_delegates_to_conversation_manager(mock_load_config, mock_conversation_manager):
    """
    Tests that the agent's run method is a simple pass-through
    to the ConversationManager's handle_prompt method.
    """
    # 1. Setup
    agent = JobSherpaAgent()
    manager_instance = mock_conversation_manager.return_value
    
    # 2. Act
    prompt = "Test prompt"
    agent.run(prompt)
    
    # 3. Assert
    manager_instance.handle_prompt.assert_called_once_with(prompt)
