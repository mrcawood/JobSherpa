import pytest
from unittest.mock import MagicMock, patch, mock_open
import yaml
import uuid
from jobsherpa.agent.actions import RunJobAction
from jobsherpa.agent.workspace_manager import JobWorkspace

# A common set of mock configs for tests
MOCK_USER_CONFIG = {"defaults": {"workspace": "/tmp", "partition": "dev", "allocation": "abc-123", "system": "mock_slurm"}}
MOCK_SYSTEM_CONFIG = {"name": "mock_slurm", "commands": {"submit": "sbatch"}, "job_requirements": ["partition", "allocation"]}
MOCK_RECIPE = {
    "name": "random_number",
    "template": "random_number.sh.j2",
    "tool": "submit",
    "output_parser": {"file": "rng.txt", "parser_regex": "Random number: (\\d+)"}
}

@pytest.fixture
def run_job_action(tmp_path):
    """Fixture to create a RunJobAction instance with mocked dependencies."""
    MOCK_USER_CONFIG["defaults"]["workspace"] = str(tmp_path)
    
    mock_history = MagicMock()
    mock_workspace_manager = MagicMock()
    mock_tool_executor = MagicMock()
    
    action = RunJobAction(
        job_history=mock_history,
        workspace_manager=mock_workspace_manager,
        tool_executor=mock_tool_executor,
        knowledge_base_dir="kb",
        user_config=MOCK_USER_CONFIG,
        system_config=MOCK_SYSTEM_CONFIG,
    )
    # Replace the real RAG pipeline with a mock for targeted testing
    action.rag_pipeline = MagicMock()
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
