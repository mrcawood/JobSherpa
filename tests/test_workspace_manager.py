import pytest
from pathlib import Path
from unittest.mock import patch
import uuid

from jobsherpa.agent.workspace_manager import WorkspaceManager, JobWorkspace

def test_workspace_manager_initialization(tmp_path):
    """
    Tests that the WorkspaceManager can be initialized with a base path.
    """
    manager = WorkspaceManager(base_path=str(tmp_path))
    assert manager.base_path == tmp_path

def test_create_job_workspace_creates_directories(tmp_path):
    """
    Tests that the create_job_workspace method physically creates the
    job directory and its internal structure.
    """
    manager = WorkspaceManager(base_path=str(tmp_path))
    
    # Mock uuid to get a predictable job directory name
    job_uuid = uuid.uuid4()
    with patch('uuid.uuid4', return_value=job_uuid):
        workspace = manager.create_job_workspace()

    expected_job_dir = tmp_path / str(job_uuid)
    
    assert expected_job_dir.is_dir()
    assert (expected_job_dir / "output").is_dir()
    assert (expected_job_dir / "slurm").is_dir()

def test_create_job_workspace_returns_correct_paths(tmp_path):
    """
    Tests that the create_job_workspace method returns a JobWorkspace
    object with the correct, fully-resolved paths.
    """
    manager = WorkspaceManager(base_path=str(tmp_path))
    
    job_uuid = uuid.uuid4()
    with patch('uuid.uuid4', return_value=job_uuid):
        workspace = manager.create_job_workspace()

    expected_job_dir = tmp_path / str(job_uuid)

    assert isinstance(workspace, JobWorkspace)
    assert workspace.job_dir == expected_job_dir
    assert workspace.output_dir == expected_job_dir / "output"
    assert workspace.slurm_dir == expected_job_dir / "slurm"
    assert workspace.script_path == expected_job_dir / "job_script.sh"
