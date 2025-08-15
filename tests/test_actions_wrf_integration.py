from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path

from jobsherpa.agent.actions import RunJobAction
from jobsherpa.agent.workspace_manager import JobWorkspace
from jobsherpa.config import UserConfig, UserConfigDefaults


def test_run_job_action_builds_wrf_context_from_kb(tmp_path, mocker):
    # Setup RunJobAction with real KB dir
    mock_job_history = MagicMock()
    mock_workspace_manager = MagicMock()
    mock_tool_executor = MagicMock()
    mock_tool_executor.execute.return_value = "Submitted batch job 12345"

    user_config = UserConfig(defaults=UserConfigDefaults(workspace=str(tmp_path), system="frontera", partition="normal", allocation="A-ccsc"))

    system_config = {
        "name": "frontera",
        "scheduler": "slurm",
        "commands": {"submit": "sbatch", "status": "squeue", "history": "sacct", "launcher": "ibrun"},
        "available_partitions": ["normal"],
        "module_init": ["ml use /scratch1/hpc_tools/benchpro-dev/modulefiles"],
    }

    action = RunJobAction(
        job_history=mock_job_history,
        workspace_manager=mock_workspace_manager,
        tool_executor=mock_tool_executor,
        knowledge_base_dir=str(Path(__file__).resolve().parents[1] / "knowledge_base"),
        user_config=user_config,
        system_config=system_config,
    )

    # Prepare job workspace and template
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True, exist_ok=True)
    mock_job_workspace = JobWorkspace(job_dir=job_dir, output_dir=job_dir / "output", slurm_dir=job_dir / "slurm", script_path=job_dir / "job_script.sh")
    mock_workspace_manager.create_job_workspace.return_value = mock_job_workspace

    # Force recipe selection to wrf
    action.recipe_index.find_best = MagicMock(return_value={
        "name": "wrf",
        "template": "wrf.sh.j2",
        "template_args": {"job_name": "wrf-run"},
        "tool": "submit",
    })

    # Run (no open patch; allow real template read and file write to tmp job dir)
    result = action.run("run wrf new conus 12km")

    # Assert that module and launcher context were used via KB
    # We can assert that the job script was written (mocked open/write) and submission was attempted
    mock_tool_executor.execute.assert_called_once()
    mock_job_history.register_job.assert_called_once()

    # Inspect rendered content
    written = (job_dir / "job_script.sh").read_text()
    assert "#SBATCH --partition" in written
    assert "#SBATCH --account" in written
    # Module init and loads
    assert "ml use" in written
    # Launcher present
    assert "ibrun" in written or "srun" in written
    # Dataset edits included (from KB dataset profile)
    assert "sed -i" in written


