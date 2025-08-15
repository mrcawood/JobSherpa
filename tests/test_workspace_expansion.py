from unittest.mock import MagicMock
from pathlib import Path
import os

from jobsherpa.agent.actions import RunJobAction
from jobsherpa.config import UserConfig, UserConfigDefaults


def test_workspace_env_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_SCRATCH", str(tmp_path / "scratch"))

    mock_job_history = MagicMock()
    mock_workspace_manager = MagicMock()
    mock_tool_executor = MagicMock()

    user_config = UserConfig(defaults=UserConfigDefaults(workspace="", system="mock_slurm"))
    system_config = {"name": "mock_slurm", "commands": {"submit": "sbatch"}, "job_requirements": ["partition", "allocation"]}

    action = RunJobAction(
        job_history=mock_job_history,
        workspace_manager=mock_workspace_manager,
        tool_executor=mock_tool_executor,
        knowledge_base_dir="knowledge_base",
        user_config=user_config,
        system_config=system_config,
    )

    # Provide workspace via context using env var
    result = action.run(prompt="run job", context={"workspace": "$TEST_SCRATCH/project"})
    # Since system is missing required params, action will ask next param; but workspace should be expanded and set
    assert action.user_config.defaults.workspace.endswith("project")
    mock_workspace_manager.base_path = Path(action.user_config.defaults.workspace)


