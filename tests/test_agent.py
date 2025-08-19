import pytest
from unittest.mock import patch, MagicMock, ANY, mock_open
from jobsherpa.agent.agent import JobSherpaAgent
from jobsherpa.config import UserConfig, UserConfigDefaults

# Decorators are applied from bottom to top.
# The mock for the first argument to the test function should be the last decorator.
@patch("builtins.open", new_callable=mock_open, read_data="name: test")
@patch("yaml.safe_load")
@patch("jobsherpa.agent.agent.ConversationManager")
def test_agent_initialization_creates_conversation_manager(
    mock_conversation_manager, mock_safe_load, mock_open
):
    """
    Tests that the agent's __init__ method correctly instantiates
    the ConversationManager with action handlers.
    """
    mock_safe_load.return_value = {"name": "test_system"}
    # Avoid initializing heavy/opaque RAG index during this unit test
    # No RAG init in RunJobAction anymore
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
@patch("jobsherpa.agent.agent.ConversationManager")
def test_agent_run_delegates_to_conversation_manager(
    mock_conversation_manager, mock_open
):
    """
    Tests that the agent's run method is a simple pass-through
    to the ConversationManager's handle_prompt method.
    """
    # This test doesn't need to mock the RAG pipeline init
    # as it's part of the RunJobAction which is mocked by ConversationManager.
    # The ZeroDivisionError was from the other test.
    # The handle_prompt error was a decorator order issue.
    # No RAG init in RunJobAction anymore
    mock_user_config = UserConfig(
        defaults=UserConfigDefaults(workspace="/tmp", system="test")
    )
    
    agent = JobSherpaAgent(
        user_config_override=mock_user_config,
        knowledge_base_dir="kb"
    )
    manager_instance = mock_conversation_manager.return_value
    manager_instance.handle_prompt.return_value = ("response", "123", False)
    
    prompt = "Test prompt"
    agent.run(prompt)
    
    manager_instance.handle_prompt.assert_called_once_with(prompt)

def test_agent_initialization_handles_missing_user_profile(mocker):
    """
    Tests that if a user profile YAML does not exist, the agent initializes
    with an empty config instead of crashing.
    """
    mocker.patch("os.path.exists", return_value=False)
    mock_safe_load = mocker.patch("yaml.safe_load")
    # No RAG init in RunJobAction anymore
    
    # We don't provide a user_config_override, so the agent will try to load one.
    agent = JobSherpaAgent(user_profile="new_user")
    
    # Assert that the agent created an empty, in-memory config.
    assert agent.workspace == ""
    # The conversation manager should not have a path, preventing save offers.
    assert agent.conversation_manager.user_profile_path is None


def test_lenient_user_profile_load_preserves_known_defaults(mocker):
    # Simulate existing profile with partial/unknown defaults
    mocker.patch("os.path.exists", return_value=True)
    raw_yaml = """
defaults:
  allocation: ABC-123
  partition: dev
  unknown_key: foo
""".strip()
    mocker.patch("builtins.open", mock_open(read_data=raw_yaml))
    # Force ConfigManager.load to fail to trigger lenient path
    mocker.patch("jobsherpa.agent.agent.ConfigManager.load", side_effect=Exception("validation error"))
    agent = JobSherpaAgent(user_profile="someone", knowledge_base_dir="kb")
    # Known fields preserved; missing requireds become empty strings
    assert agent.workspace == ""
    # Access run_job_action's user_config via conversation manager
    rja = agent.conversation_manager._pending_action or agent.conversation_manager.run_job_action
    assert rja.user_config.defaults.allocation == "ABC-123"
    assert rja.user_config.defaults.partition == "dev"
