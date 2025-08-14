import pytest
from unittest.mock import patch, MagicMock, ANY, mock_open
from jobsherpa.agent.agent import JobSherpaAgent
from jobsherpa.config import UserConfig, UserConfigDefaults

# Decorators are applied from bottom to top.
# The mock for the first argument to the test function should be the last decorator.
@patch("builtins.open", new_callable=mock_open, read_data="name: test")
@patch("yaml.safe_load")
@patch("jobsherpa.agent.actions.RunJobAction._initialize_rag_pipeline")
@patch("jobsherpa.agent.agent.ConversationManager")
def test_agent_initialization_creates_conversation_manager(
    mock_conversation_manager, mock_rag_init, mock_safe_load, mock_open
):
    """
    Tests that the agent's __init__ method correctly instantiates
    the ConversationManager with action handlers.
    """
    mock_safe_load.return_value = {"name": "test_system"}
    # Avoid initializing heavy/opaque RAG index during this unit test
    mock_rag_init.return_value = MagicMock()
    mock_user_config = UserConfig(
        defaults=UserConfigDefaults(workspace="/tmp", system="test")
    )
    
    agent = JobSherpaAgent(user_config_override=mock_user_config)
    
    mock_conversation_manager.assert_called_once()
    # Check that the action handlers were created and passed to the manager
    call_args, call_kwargs = mock_conversation_manager.call_args
    assert "run_job_action" in call_kwargs
    assert "query_history_action" in call_kwargs

@patch("builtins.open", new_callable=mock_open, read_data="name: test")
@patch("jobsherpa.agent.actions.RunJobAction._initialize_rag_pipeline")
@patch("jobsherpa.agent.agent.ConversationManager")
def test_agent_run_delegates_to_conversation_manager(
    mock_conversation_manager, mock_rag_init, mock_open
):
    """
    Tests that the agent's run method is a simple pass-through
    to the ConversationManager's handle_prompt method.
    """
    # This test doesn't need to mock the RAG pipeline init
    # as it's part of the RunJobAction which is mocked by ConversationManager.
    # The ZeroDivisionError was from the other test.
    # The handle_prompt error was a decorator order issue.
    mock_rag_init.return_value = MagicMock()
    mock_user_config = UserConfig(
        defaults=UserConfigDefaults(workspace="/tmp", system="test")
    )
    
    agent = JobSherpaAgent(
        user_config_override=mock_user_config,
        knowledge_base_dir="kb"
    )
    manager_instance = mock_conversation_manager.return_value
    
    prompt = "Test prompt"
    agent.run(prompt)
    
    manager_instance.handle_prompt.assert_called_once_with(prompt)
