import subprocess
import logging
from typing import Dict, List


logger = logging.getLogger(__name__)


class SchedulerClient:
    """
    Abstract interface for querying a scheduler about job statuses.
    Implementations must return normalized status strings.
    """

    def get_active_statuses(self, job_ids: List[str]) -> Dict[str, str]:
        """Return statuses for actively running/pending jobs (e.g., via squeue)."""
        raise NotImplementedError

    def get_final_statuses(self, job_ids: List[str]) -> Dict[str, str]:
        """Return final statuses for completed jobs (e.g., via sacct)."""
        raise NotImplementedError


class SlurmSchedulerClient(SchedulerClient):
    """
    SLURM implementation using subprocess to call squeue/sacct.
    """

    def get_active_statuses(self, job_ids: List[str]) -> Dict[str, str]:
        if not job_ids:
            return {}
        command = [
            "squeue",
            "--jobs=" + ",".join(job_ids),
            "--noheader",
            "--format=%i,%T",
        ]
        logger.debug("Running squeue command: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stderr:
            logger.warning("squeue returned stderr: %s", result.stderr)
        statuses: Dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split(",")
            if len(parts) == 2:
                job_id, state = parts[0].strip(), parts[1].strip()
                statuses[job_id] = self._normalize_active_state(state)
        return statuses

    def get_final_statuses(self, job_ids: List[str]) -> Dict[str, str]:
        if not job_ids:
            return {}
        command = [
            "sacct",
            "--jobs=" + ",".join(job_ids),
            "--noheader",
            "--format=JobId,State,ExitCode",
        ]
        logger.debug("Running sacct command: %s", " ".join(command))
        result = subprocess.run(command, capture_output=True, text=True)
        if result.stderr:
            logger.warning("sacct returned stderr: %s", result.stderr)
        statuses: Dict[str, str] = {}
        for line in result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) > 1:
                job_id_raw, state = parts[0].strip(), parts[1].strip()
                # Map to the requested job id(s)
                for target_id in job_ids:
                    if job_id_raw.startswith(target_id):
                        statuses[target_id] = self._normalize_final_state(state)
                        break
        return statuses

    def _normalize_active_state(self, state: str) -> str:
        s = state.strip().upper()
        if s in {"PENDING", "RUNNING"}:
            return s
        return s

    def _normalize_final_state(self, state: str) -> str:
        s = state.strip().upper()
        if s in {"COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"}:
            return s
        return s


