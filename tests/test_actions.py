import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml
import uuid
from jobsherpa.agent.actions import RunJobAction
from jobsherpa.agent.workspace_manager import JobWorkspace
from jobsherpa.agent.actions import QueryHistoryAction

# A common set of mock configs for tests
MOCK_USER_CONFIG = {"defaults": {"workspace": "/tmp", "partition": "dev", "allocation": "abc-123", "system": "mock_slurm"}}
MOCK_SYSTEM_CONFIG = {"name": "mock_slurm", "commands": {"submit": "sbatch"}, "job_requirements": ["partition", "allocation"]}
MOCK_RECIPE = {
    "name": "random_number",
    "template": "random_number.sh.j2",
    "tool": "submit",
    "output_parser": {"file": "rng.txt", "parser_regex": "Random number: (\\d+)"}
}
MOCK_NON_TEMP_RECIPE = {"name": "hello_world", "tool": "echo", "args": ["hello"]}

@pytest.fixture
def run_job_action(tmp_path):
    """Fixture to create a RunJobAction instance with mocked dependencies."""
    # Reset the system config to a clean state for each test
    system_config = {
        "name": "mock_slurm",
        "commands": {"submit": "sbatch"},
        "job_requirements": ["partition", "allocation"]
    }
    
    mock_history = MagicMock()
    mock_workspace_manager = MagicMock()
    mock_tool_executor = MagicMock()
    
    action = RunJobAction(
        job_history=mock_history,
        workspace_manager=mock_workspace_manager,
        tool_executor=mock_tool_executor,
        knowledge_base_dir="kb",
        user_config=MOCK_USER_CONFIG,
        system_config=system_config,
    )
    # Replace the real RAG pipeline with a mock for targeted testing
    action.rag_pipeline = MagicMock()
    return action

@pytest.fixture
def query_history_action():
    """Fixture to create a QueryHistoryAction instance with a mocked JobHistory."""
    mock_history = MagicMock()
    return QueryHistoryAction(job_history=mock_history)

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

    # 2. Act
    with patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("builtins.open", mock_open()) as m_open:
        response, job_id = run_job_action.run("prompt")

    # 3. Assert
    # Assert RAG and workspace were used
    run_job_action.rag_pipeline.run.assert_called_once()
    run_job_action.workspace_manager.create_job_workspace.assert_called_once()

    # Assert template rendering
    mock_template.render.assert_called_once()
    context = mock_template.render.call_args.args[0]
    assert context['partition'] == 'dev'
    assert context['allocation'] == 'abc-123'
    assert context['job_dir'] == str(mock_job_workspace.job_dir)
    
    # Assert script was written and executed
    m_open.assert_called_with(mock_job_workspace.script_path, 'w')
    m_open().write.assert_called_with("script content")
    run_job_action.tool_executor.execute.assert_called_with(
        "sbatch", [mock_job_workspace.script_path.name], workspace=str(job_dir)
    )

    # Assert job was registered with history
    run_job_action.job_history.register_job.assert_called_once()
    registered_job_id = run_job_action.job_history.register_job.call_args.args[0]
    assert registered_job_id == "12345"

def test_run_job_action_fails_with_missing_requirements(run_job_action):
    """
    Tests that the action fails gracefully if the merged config is missing
    parameters defined in the system's 'job_requirements'.
    """
    # 1. Setup
    # Create a system config with a requirement the user config doesn't have
    run_job_action.system_config["job_requirements"] = ["some_other_thing"]
    run_job_action.rag_pipeline.run.return_value = {"documents": [MagicMock(meta=MOCK_RECIPE)]}

    # 2. Act
    response, job_id = run_job_action.run("prompt")

    # 3. Assert
    assert "Missing required job parameters" in response
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

    # 2. Act
    response, job_id = run_job_action.run("prompt")

    # 3. Assert
    # Assert RAG was used
    run_job_action.rag_pipeline.run.assert_called_once()
    
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

    # 2. Act
    with patch("jinja2.Environment.get_template", return_value=mock_template), \
         patch("builtins.open", mock_open()):
        response, job_id = run_job_action.run("prompt")

    # 3. Assert
    # Assert that the submission was attempted
    run_job_action.tool_executor.execute.assert_called_once()
    
    # Assert that no job was registered
    run_job_action.job_history.register_job.assert_not_called()
    
    # Assert that the response contains the error from the tool
    assert job_id is None
    assert "Execution result: sbatch: error: Invalid project account" in response

def test_query_history_action_gets_last_job_result(query_history_action):
    """
    Tests that the action can retrieve the result of the most recent job.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_latest_job_id.return_value = "job_5"
    mock_history.get_status.return_value = "COMPLETED"
    mock_history.get_result.return_value = "42"
    
    # 2. Act
    response = query_history_action.run("what was the result of my last job?")
    
    # 3. Assert
    mock_history.get_latest_job_id.assert_called_once()
    mock_history.get_status.assert_called_with("job_5")
    mock_history.get_result.assert_called_with("job_5")
    assert "The result of job job_5 (COMPLETED) is: 42" in response

def test_query_history_action_gets_job_by_id(query_history_action):
    """
    Tests that the action can retrieve the result of a specific job by its ID.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_status.return_value = "COMPLETED"
    mock_history.get_result.return_value = "Success"

    # 2. Act
    response = query_history_action.run("tell me about job 12345")

    # 3. Assert
    mock_history.get_status.assert_called_with("12345")
    mock_history.get_result.assert_called_with("12345")
    assert "The result of job 12345 (COMPLETED) is: Success" in response

def test_query_history_action_handles_job_not_found(query_history_action):
    """
    Tests that a user-friendly message is returned for a job ID that doesn't exist.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_status.return_value = None

    # 2. Act
    response = query_history_action.run("tell me about job 99999")

    # 3. Assert
    mock_history.get_status.assert_called_with("99999")
    mock_history.get_result.assert_not_called()
    assert "Sorry, I couldn't find any information for job ID 99999." in response

def test_query_history_action_handles_running_job(query_history_action):
    """
    Tests that a helpful message is returned for a job that is not yet complete.
    """
    # 1. Setup
    mock_history = query_history_action.job_history
    mock_history.get_status.return_value = "RUNNING"
    mock_history.get_result.return_value = None

    # 2. Act
    response = query_history_action.run("what is the result of job 12345")

    # 3. Assert
    mock_history.get_status.assert_called_with("12345")
    mock_history.get_result.assert_called_with("12345")
    assert "Job 12345 is still RUNNING. The result is not yet available." in response
