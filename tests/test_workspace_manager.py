import pytest
from pathlib import Path
from unittest.mock import patch
import uuid
from datetime import datetime
from freezegun import freeze_time

from jobsherpa.agent.workspace_manager import WorkspaceManager, JobWorkspace

def test_workspace_manager_initialization(tmp_path):
    """
    Tests that the WorkspaceManager can be initialized with a base path.
    """
    manager = WorkspaceManager(base_path=str(tmp_path))
    assert manager.base_path == tmp_path

@freeze_time("2025-08-14 12:30:00")
@patch("uuid.uuid4")
def test_create_job_workspace_creates_directories(mock_uuid, tmp_path):
    """
    Tests that the create_job_workspace method physically creates the
    job directory and its internal structure using the new naming convention.
    """
    mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
    manager = WorkspaceManager(base_path=str(tmp_path))

    workspace = manager.create_job_workspace()

    expected_dir_name = "2025-08-14-12-30-jobsherpa_run-123456"
    expected_job_dir = tmp_path / expected_dir_name

    assert expected_job_dir.is_dir()
    assert (expected_job_dir / "output").is_dir()
    assert (expected_job_dir / "slurm").is_dir()

@freeze_time("2025-08-14 12:30:00")
@patch("uuid.uuid4")
def test_create_job_workspace_returns_correct_paths(mock_uuid, tmp_path):
    """
    Tests that the create_job_workspace method returns a JobWorkspace
    object with the correct, fully-resolved paths using the new naming convention.
    """
    mock_uuid.return_value = uuid.UUID('12345678-1234-5678-1234-567812345678')
    manager = WorkspaceManager(base_path=str(tmp_path))

    workspace = manager.create_job_workspace()

    expected_dir_name = "2025-08-14-12-30-jobsherpa_run-123456"
    expected_job_dir = tmp_path / expected_dir_name

    assert isinstance(workspace, JobWorkspace)
    assert workspace.job_dir == expected_job_dir
    assert workspace.output_dir == expected_job_dir / "output"
    assert workspace.slurm_dir == expected_job_dir / "slurm"
    assert workspace.script_path == expected_job_dir / "job_script.sh"
