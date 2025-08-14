from dataclasses import dataclass
from pathlib import Path
import uuid
import os

@dataclass
class JobWorkspace:
    """A data class to hold the paths for a specific job's workspace."""
    job_dir: Path
    output_dir: Path
    slurm_dir: Path
    script_path: Path

class WorkspaceManager:
    """Manages the creation of isolated job directories within a base workspace."""
    
    def __init__(self, base_path: str):
        """
        Initializes the manager with the root path for all job workspaces.
        """
        self.base_path = Path(base_path)

    def create_job_workspace(self) -> JobWorkspace:
        """
        Creates a new, unique, isolated directory structure for a single job run.

        Returns:
            JobWorkspace: A dataclass containing the paths to the new directories.
        """
        job_id = str(uuid.uuid4())
        job_dir = self.base_path / job_id
        
        output_dir = job_dir / "output"
        slurm_dir = job_dir / "slurm"
        
        # Create all directories
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(slurm_dir, exist_ok=True)

        return JobWorkspace(
            job_dir=job_dir,
            output_dir=output_dir,
            slurm_dir=slurm_dir,
            script_path=job_dir / "job_script.sh"
        )
