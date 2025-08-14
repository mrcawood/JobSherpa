from dataclasses import dataclass
from pathlib import Path
import uuid
import os
from datetime import datetime

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

    def create_job_workspace(self, job_name: str = "jobsherpa-run") -> JobWorkspace:
        """
        Creates a new, uniquely named job directory.

        The directory format is YYYY-MM-DD-HH-MM-{{job_name}}-{{6_digit_hash}}.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M")
        # Replace problematic characters with underscores
        safe_job_name = job_name.replace(" ", "_").replace("/", "_").replace("-", "_")
        unique_hash = str(uuid.uuid4().hex)[:6]
        
        dir_name = f"{timestamp}-{safe_job_name}-{unique_hash}"
        job_dir = self.base_path / dir_name
        
        output_dir = job_dir / "output"
        slurm_dir = job_dir / "slurm"
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(slurm_dir, exist_ok=True)
        
        return JobWorkspace(
            job_dir=job_dir,
            output_dir=output_dir,
            slurm_dir=slurm_dir,
            script_path=job_dir / "job_script.sh"
        )
