import pytest
from unittest.mock import MagicMock, patch, mock_open, ANY
import yaml
import uuid
from jobsherpa.agent.actions import RunJobAction
from jobsherpa.agent.workspace_manager import JobWorkspace
from jobsherpa.agent.actions import QueryHistoryAction
from jobsherpa.config import UserConfig, UserConfigDefaults
from pathlib import Path

# A common set of mock configs for tests
MOCK_USER_CONFIG = {"defaults": {"workspace": "/tmp", "partition": "dev", "allocation": "abc-123", "system": "mock_slurm"}}
MOCK_SYSTEM_CONFIG = {"name": "mock_slurm", "commands": {"submit": "sbatch"}, "job_requirements": ["partition", "allocation"]}
MOCK_RECIPE = {
    "name": "random_number",
    "template": "random_number.sh.j2",
    "tool": "submit",
    "template_args": {"job_name": "test-job"},
    "output_parser": {"file": "rng.txt", "parser_regex": "Random number: (\\d+)"}
}
MOCK_NON_TEMP_RECIPE = {"name": "hello_world", "tool": "echo", "args": ["hello"]}
MOCK_RECIPE_WITH_TEMPLATE_IN_PARSER = {
    "name": "random_number",
    "template": "random_number.sh.j2",
    "tool": "submit",
    "template_args": {"output_file": "my_rng.txt", "job_name": "test-job"},
    "output_parser": {"file": "{{ output_file }}", "parser_regex": "Random number: (\\d+)"}
}

@pytest.fixture
def run_job_action(mocker, tmp_path):
    """Fixture to create a RunJobAction instance with mocked dependencies."""
    mock_job_history = MagicMock()
    mock_workspace_manager = MagicMock()
    mock_tool_executor = MagicMock()
    mock_tool_executor.execute.return_value = "Submitted batch job 12345"
    
    # Use a Pydantic object for the user_config to match the new system
    user_config = UserConfig(
        defaults=UserConfigDefaults(
            workspace=str(tmp_path),
            system="mock_slurm",
            partition="development",
            allocation="test-alloc"
        )
    )
    
    # Create a fresh copy of the system config for each test to prevent state leakage
    system_config = MOCK_SYSTEM_CONFIG.copy()
    
    action = RunJobAction(
        job_history=mock_job_history,
        workspace_manager=mock_workspace_manager,
        tool_executor=mock_tool_executor,
        knowledge_base_dir=str(tmp_path), # Use tmp_path to avoid real file system
        user_config=user_config,
        system_config=system_config,
    )
    
    # Replace RAG pipeline with a MagicMock so tests can control and assert calls safely
    action.rag_pipeline = MagicMock()
    action.rag_pipeline.run = MagicMock()
    return action

@pytest.fixture
def query_history_action(mocker):
    """Fixture to create a QueryHistoryAction instance with a mocked JobHistory."""
    mock_history = MagicMock()
    action = QueryHistoryAction(job_history=mock_history)
    return action

def test_run_job_action_renders_and_executes_template(run_job_action, tmp_path):
    """
    Tests that RunJobAction can correctly find a recipe, render the template,
    and execute the submission command within the correct job-specific directory.
    """
    # 1. Setup
    job_uuid = uuid.uuid4()
    job_dir = tmp_path / str(job_uuid)
    mock_job_workspace = JobWorkspace(
        job_dir=job_dir, output_dir=job_dir / "output", slurm_dir=job_dir / "slurm", script_path=job_dir / "job_script.sh"
    )
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_RECIPE)]}
    run_job_action.workspace_manager.create_job_workspace.return_value = mock_job_workspace
    run_job_action.tool_executor.execute.return_value = "Submitted batch job 12345"
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_RECIPE)

    # 2. Act
    with patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("builtins.open", mock_open()) as m_open:
        response, job_id, _, _ = run_job_action.run("prompt")

    # 3. Assert
    # Assert RAG and workspace were used
    # run_job_action.rag_pipeline.run.assert_called_once() # <-- This is now bypassed
    run_job_action.workspace_manager.create_job_workspace.assert_called_once()
    
    # Assert template was rendered with correct context
    mock_template.render.assert_called_once()
    context = mock_template.render.call_args.args[0]
    assert context['partition'] == 'development'
    assert context['allocation'] == 'test-alloc'
    assert context['job_dir'] == str(mock_job_workspace.job_dir)
    
    # Assert script was written and executed
    m_open.assert_called_with(mock_job_workspace.script_path, 'w')
    m_open().write.assert_called_with("script content")
    run_job_action.tool_executor.execute.assert_called_with(
        "sbatch", [mock_job_workspace.script_path.name], workspace=str(job_dir)
    )

    # Assert job was registered with history
    run_job_action.job_history.register_job.assert_called_once_with(
        job_id="12345",
        job_name="test-job",
        job_directory=str(mock_job_workspace.job_dir),
        output_parser_info=ANY
    )

def test_run_job_action_fails_with_missing_requirements(run_job_action):
    """
    Tests that the action fails gracefully if the merged config is missing
    parameters defined in the system's 'job_requirements'.
    """
    # 1. Setup
    # Create a system config with a requirement the user config doesn't have
    run_job_action.system_config["job_requirements"] = ["some_other_thing"]
    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_RECIPE)]}
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_RECIPE)

    # 2. Act
    response, job_id, _, _ = run_job_action.run("prompt")

    # 3. Assert
    assert "I need a value for 'some_other_thing'" in response
    assert job_id is None
    run_job_action.tool_executor.execute.assert_not_called()

def test_run_job_action_executes_non_templated_job(run_job_action):
    """
    Tests that the action handler can correctly execute a simple job
    that does not use a template.
    """
    # 1. Setup
    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_NON_TEMP_RECIPE)]}
    run_job_action.tool_executor.execute.return_value = "hello" # No job ID for this simple command
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_NON_TEMP_RECIPE)

    # 2. Act
    response, job_id, _, _ = run_job_action.run("prompt")

    # 3. Assert
    # RAG is not invoked when _find_matching_recipe is mocked directly
    
    # Assert the correct tool and args were executed in the base workspace
    run_job_action.tool_executor.execute.assert_called_with(
        "echo", ["hello"], workspace=run_job_action.workspace_manager.base_path
    )
    
    # Assert no job was registered, as no job ID was returned
    run_job_action.job_history.register_job.assert_not_called()
    assert job_id is None
    assert "Execution result: hello" in response

def test_run_job_action_handles_job_submission_failure(run_job_action, tmp_path):
    """
    Tests that the action handles the case where the tool executor
    does not return a valid job ID string.
    """
    # 1. Setup
    # This test should not be affected by state from other tests
    assert "some_other_thing" not in run_job_action.system_config["job_requirements"]
    
    job_uuid = uuid.uuid4()
    job_dir = tmp_path / str(job_uuid)
    mock_job_workspace = JobWorkspace(
        job_dir=job_dir, output_dir=job_dir / "output", slurm_dir=job_dir / "slurm", script_path=job_dir / "job_script.sh"
    )
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_RECIPE)]}
    run_job_action.workspace_manager.create_job_workspace.return_value = mock_job_workspace
    # Simulate a failed submission (e.g., sbatch returns an error)
    run_job_action.tool_executor.execute.return_value = "sbatch: error: Invalid project account"
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_RECIPE)

    # 2. Act
    with patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("builtins.open", mock_open()):
        response, job_id, _, _ = run_job_action.run("prompt")

    # 3. Assert
    # Assert that the submission was attempted
    run_job_action.tool_executor.execute.assert_called_once()
    
    # Assert that no job was registered
    run_job_action.job_history.register_job.assert_not_called()
    
    # Assert that the response contains the error from the tool
    assert job_id is None
    assert "Execution result: sbatch: error: Invalid project account" in response

def test_query_history_action_routes_to_status(query_history_action):
    query_history_action._get_last_job_status = MagicMock()
    query_history_action._get_last_job_result = MagicMock()
    query_history_action.run("what is the status of my last job")
    query_history_action._get_last_job_status.assert_called_once()
    query_history_action._get_last_job_result.assert_not_called()

def test_query_history_action_routes_to_result(query_history_action):
    query_history_action._get_last_job_status = MagicMock()
    query_history_action._get_last_job_result = MagicMock()
    query_history_action.run("what was the result of my last job?")
    query_history_action._get_last_job_status.assert_not_called()
    query_history_action._get_last_job_result.assert_called_once()

# We still need a test for the actual implementation of the tool method
def test_get_last_job_status_implementation(mocker):
    # We create a clean instance for this test so the internal method is not mocked
    mock_history = MagicMock()
    action = QueryHistoryAction(job_history=mock_history)
    
    # 1. Setup
    mock_job = {
        "job_id": "12345",
        "status": "COMPLETED",
        "result": "Random number: 42"
    }
    action.job_history.get_latest_job.return_value = mock_job
    action.job_history.get_status.return_value = "COMPLETED"

    # 2. Act
    response = action._get_last_job_status()
    
    # 3. Assert
    assert response == "The status of job 12345 is COMPLETED."
    action.job_history.get_latest_job.assert_called_once()

def test_get_last_job_result_implementation(mocker):
    # We create a clean instance for this test so the internal method is not mocked
    mock_history = MagicMock()
    action = QueryHistoryAction(job_history=mock_history)
    
    # 1. Setup
    action.job_history.get_latest_job_id.return_value = "job_5"
    action.job_history.get_result.return_value = "42"
    
    # 2. Act
    response = action._get_last_job_result()
    
    # 3. Assert
    assert "The result of job job_5 is: 42" in response
    action.job_history.get_latest_job_id.assert_called_once()

def test_query_history_action_handles_job_not_found(query_history_action):
    """
    Tests that a user-friendly message is returned for a job ID that doesn't exist.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_job_by_id.return_value = None

    # 2. Act
    response = query_history_action.run("tell me about job 99999")

    # 3. Assert
    query_history_action.job_history.get_job_by_id.assert_called_with("99999")
    assert "Sorry, I couldn't find any information for job ID 99999." in response

def test_query_history_action_handles_running_job(query_history_action):
    """
    Tests that a helpful message is returned for a job that is not yet complete.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_job_by_id.return_value = {"result": None}
    mock_history.check_job_status.return_value = "RUNNING"

    # 2. Act
    response = query_history_action.run("what is the result of job 12345")

    # 3. Assert
    query_history_action.job_history.get_job_by_id.assert_called_with("12345")
    assert "Job 12345 status is RUNNING" in response

def test_run_job_action_renders_output_parser_file(run_job_action, tmp_path):
    """
    Tests that if the output_parser's 'file' field is a template,
    it is correctly rendered before being sent to the JobHistory.
    """
    # 1. Setup
    job_uuid = uuid.uuid4()
    job_dir = tmp_path / str(job_uuid)
    mock_job_workspace = JobWorkspace(
        job_dir=job_dir, output_dir=job_dir / "output", slurm_dir=job_dir / "slurm", script_path=job_dir / "job_script.sh"
    )
    mock_template = MagicMock()
    mock_template.render.return_value = "script content"

    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_RECIPE_WITH_TEMPLATE_IN_PARSER)]}
    run_job_action.workspace_manager.create_job_workspace.return_value = mock_job_workspace
    run_job_action.tool_executor.execute.return_value = "Submitted batch job 12345"
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_RECIPE_WITH_TEMPLATE_IN_PARSER)

    # 2. Act
    with patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("builtins.open", mock_open()):
        run_job_action.run("prompt")

    # 3. Assert
    run_job_action.job_history.register_job.assert_called_once()
    run_job_action.job_history.register_job.assert_called_with(
        job_id="12345",
        job_name="test-job",
        job_directory=str(mock_job_workspace.job_dir),
        output_parser_info=ANY
    )

def test_run_job_action_asks_for_missing_parameters(run_job_action):
    """
    Tests that if a required parameter is missing, RunJobAction returns
    a question asking for the missing information.
    """
    # 1. Setup: Make 'allocation' a missing parameter
    run_job_action.user_config.defaults.allocation = None
    run_job_action.system_config["job_requirements"] = ["allocation"]
    run_job_action._find_matching_recipe = MagicMock(return_value=MOCK_RECIPE)
    
    # 2. Act
    response, job_id, is_waiting, param_needed = run_job_action.run(prompt="Run the random number generator")
    
    # 3. Assert
    assert job_id is None
    assert is_waiting is True
    assert param_needed == "allocation"
    assert "I need a value for 'allocation'" in response

def test_run_job_action_gathers_workspace_and_system_from_context(run_job_action, mocker):
    """
    Tests that if the agent starts with no config, it can gather the workspace
    and system from the conversational context and load them correctly.
    """
    # 1. Setup: Start with an empty user config and no system config
    run_job_action.user_config.defaults.workspace = ""
    run_job_action.system_config = None
    run_job_action.workspace_manager.base_path = None
    
    # Mock os.path.exists to simulate finding the system file
    mocker.patch("os.path.exists", return_value=True)
    # Mock open to provide the system file content
    mocked_open = mock_open(read_data="name: mock_slurm")
    mocker.patch("builtins.open", mocked_open)

    # 2. Act: Provide the workspace in the first turn
    response, _, _, _ = run_job_action.run(prompt="run job", context={"workspace": "/tmp/test_ws"})
    assert response == "I need a system profile to run this job. What system should I use?"
    
    # 3. Act: Provide the system in the second turn
    response, _, _, _ = run_job_action.run(prompt="run job", context={"workspace": "/tmp/test_ws", "system": "mock_slurm"})
    
    # 4. Assert: The action now proceeds to the RAG step (or fails there, which is fine)
    assert "I need a system profile" not in response
    assert "I need a workspace" not in response
    assert run_job_action.system_config["name"] == "mock_slurm"
    assert run_job_action.workspace_manager.base_path == Path("/tmp/test_ws")

def test_query_history_action_routes_to_id_query(query_history_action):
    """
    Tests that a query containing a job ID is correctly routed.
    """
    query_history_action._get_job_by_id_summary = MagicMock(return_value="Summary for job 12345")
    query_history_action.run("what is the status of job 12345")
    query_history_action._get_job_by_id_summary.assert_called_once_with("12345")
