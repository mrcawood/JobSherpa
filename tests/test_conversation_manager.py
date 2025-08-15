import pytest
from unittest.mock import MagicMock

from jobsherpa.agent.conversation_manager import ConversationManager
from jobsherpa.agent.types import ActionResult

def test_conversation_manager_routes_to_run_job_action():
    """
    Tests that a 'run_job' intent correctly calls the RunJobAction handler.
    """
    # 1. Setup Mocks
    mock_classifier = MagicMock()
    mock_run_job_action = MagicMock()
    mock_query_history_action = MagicMock()
    
    mock_classifier.classify.return_value = "run_job"
    mock_run_job_action.run.return_value = ActionResult(message="Success", job_id="12345", is_waiting=False)
    
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
    mock_query_history_action.run.return_value = "Some history response"
    
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
    mock_run_job_action.run.return_value = ActionResult(message="I need an allocation...", is_waiting=True, param_needed="allocation")
    
    response, _, _ = manager.handle_prompt("Run my job")
    
    # Assert that the manager asked the question and is now waiting for a response
    assert "I need an allocation" in response
    assert manager.is_waiting_for_input()
    
    # --- Turn 2: User provides the missing allocation ---
    # The intent should not be re-classified; the manager should use the context
    mock_intent_classifier.reset_mock()
    # Simulate RunJobAction now succeeding with the new context
    mock_run_job_action.run.return_value = ActionResult(message="Job submitted with ID: 12345", job_id="12345", is_waiting=False)
    
    response, _, _ = manager.handle_prompt("use allocation abc-123")
    
    # Assert that the manager used the new context and submitted the job
    mock_intent_classifier.classify.assert_not_called()
    mock_run_job_action.run.assert_called_with(
        prompt="Run my job",
        context={"allocation": "use allocation abc-123"}
    )
    assert "Job submitted with ID: 12345" in response
    assert not manager.is_waiting_for_input()

def test_conversation_manager_offers_to_save_multiple_parameters(mocker):
    """
    Tests the full multi-turn flow where the agent:
    1. Asks for multiple missing parameters.
    2. Submits the job with the provided parameters.
    3. Asks the user if they want to save all the new parameters.
    4. Saves the configuration upon user confirmation.
    """
    # 1. Setup
    mock_intent_classifier = MagicMock()
    mock_run_job_action = MagicMock()
    mock_query_history_action = MagicMock()
    mock_config_manager_class = mocker.patch("jobsherpa.agent.conversation_manager.ConfigManager")
    mock_config_manager_instance = mock_config_manager_class.return_value
    
    mock_user_config = MagicMock()
    mock_config_manager_instance.load.return_value = mock_user_config

    manager = ConversationManager(
        intent_classifier=mock_intent_classifier,
        run_job_action=mock_run_job_action,
        query_history_action=mock_query_history_action,
        user_profile_path="/fake/path/user.yaml",
    )
    
    # --- Turn 1: Ask for 'allocation' ---
    mock_run_job_action.run.return_value = ActionResult(message="I need an allocation.", is_waiting=True, param_needed="allocation")
    response, _, is_waiting = manager.handle_prompt("Run my job")
    assert "I need an allocation" in response
    assert is_waiting is True

    # --- Turn 2: User provides 'allocation', agent asks for 'partition' ---
    mock_run_job_action.run.return_value = ActionResult(message="I need a partition.", is_waiting=True, param_needed="partition")
    response, _, is_waiting = manager.handle_prompt("use-this-alloc")
    assert "I need a partition" in response
    assert is_waiting is True

    # --- Turn 3: User provides 'partition', job succeeds, agent offers to save ---
    mock_run_job_action.run.return_value = ActionResult(message="Job submitted with ID: 12345", job_id="12345", is_waiting=False)
    response, _, is_waiting = manager.handle_prompt("use-this-partition")
    assert "Job submitted" in response
    assert "Would you like to save {'allocation': 'use-this-alloc', 'partition': 'use-this-partition'}" in response
    assert is_waiting is True

    # --- Turn 4: User confirms the save ---
    response, _, is_waiting = manager.handle_prompt("yes")
    # ... (assertions for saving)
    assert mock_user_config.defaults.allocation == "use-this-alloc"
    assert mock_user_config.defaults.partition == "use-this-partition"
    assert "Configuration saved!" in response
    assert is_waiting is False
