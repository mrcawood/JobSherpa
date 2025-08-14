import time
import subprocess
import re
import logging
from typing import Optional
import os
import json

logger = logging.getLogger(__name__)

class JobHistory:
    """
    Manages the state of active and completed jobs, with persistence.
    """
    def __init__(self, history_file_path: Optional[str] = None):
        self.history_file_path = history_file_path
        self._jobs = self._load_state()

    def _load_state(self) -> dict:
        """Loads the job history from the JSON file."""
        if self.history_file_path and os.path.exists(self.history_file_path):
            try:
                with open(self.history_file_path, 'r') as f:
                    logger.debug("Loading job history from %s", self.history_file_path)
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.error("Failed to load job history file: %s", e)
        return {}

    def _save_state(self):
        """Saves the current job history to the JSON file."""
        if self.history_file_path:
            try:
                with open(self.history_file_path, 'w') as f:
                    json.dump(self._jobs, f, indent=4)
                    logger.debug("Saved job history to %s", self.history_file_path)
            except IOError as e:
                logger.error("Failed to save job history file: %s", e)

    def register_job(self, job_id: str, job_directory: str, output_parser_info: Optional[dict] = None):
        """
        Registers a new job with a default 'PENDING' status.
        """
        if job_id not in self._jobs:
            self._jobs[job_id] = {
                "status": "PENDING",
                "start_time": time.time(),
                "job_directory": job_directory,
                "output_parser": output_parser_info,
                "result": None
            }
            logger.info("Registered new job: %s in directory: %s", job_id, job_directory)
            self._save_state()

    def get_status(self, job_id: str) -> Optional[str]:
        """
        Gets the status of a specific job. If the job is in a non-terminal
        state, it actively checks for an update before returning.
        """
        current_status = self._jobs.get(job_id, {}).get("status")

        # If we don't know the job, or it's already finished, return the stored status.
        if not current_status or current_status in ["COMPLETED", "FAILED", "CANCELLED", "TIMEOUT"]:
            return current_status

        # Otherwise, the job is PENDING or RUNNING, so check for a real-time update.
        logger.debug("Actively checking status for non-terminal job: %s", job_id)
        self.check_and_update_statuses(specific_job_id=job_id)

        # Return the potentially updated status
        return self._jobs.get(job_id, {}).get("status")

    def set_status(self, job_id: str, new_status: str):
        """
        Updates the status of a specific job.
        """
        if job_id in self._jobs:
            if self._jobs[job_id]["status"] != new_status:
                logger.info("Job %s status changed to: %s", job_id, new_status)
            self._jobs[job_id]["status"] = new_status
            # If job is done, try to parse its output
            if new_status == "COMPLETED" and self._jobs[job_id].get("output_parser"):
                self._parse_job_output(job_id)
            self._save_state()
    
    def get_result(self, job_id: str) -> Optional[str]:
        """Gets the parsed result of a completed job."""
        return self._jobs[job_id].get("result") if job_id in self._jobs else None

    def get_latest_job_id(self) -> Optional[str]:
        """Returns the ID of the most recently submitted job."""
        if not self._jobs:
            return None
        
        # Find the job with the maximum start_time
        latest_job_id = max(self._jobs, key=lambda j: self._jobs[j].get("start_time", 0))
        return latest_job_id

    def get_all_jobs(self) -> dict:
        """Returns the entire dictionary of jobs."""
        return self._jobs

    def _parse_job_output(self, job_id: str):
        """Parses the output file of a completed job to find a result."""
        job_info = self._jobs.get(job_id)
        if not job_info or not job_info.get("output_parser"):
            return

        parser_info = job_info["output_parser"]
        relative_output_file = parser_info.get("file")
        job_directory = job_info.get("job_directory")
        regex_pattern = parser_info.get("parser_regex")

        if not all([relative_output_file, job_directory, regex_pattern]):
            logger.warning("Job %s is missing information required for output parsing.", job_id)
            return

        # The output file path is now relative to the job's unique directory
        output_file_path = os.path.join(job_directory, relative_output_file)
        
        logger.info("Parsing output file '%s' for job %s", output_file_path, job_id)
        try:
            with open(output_file_path, 'r') as f:
                content = f.read()
            
            match = re.search(regex_pattern, content)
            if match:
                result = match.group(1)
                self._jobs[job_id]["result"] = result
                logger.info("Parsed result for job %s: %s", job_id, result)
                self._save_state() # Save state after successful parsing
            else:
                logger.warning("Regex did not find a match in output file for job %s", job_id)
        except FileNotFoundError:
            logger.warning("Could not find output file %s to parse for job %s.", output_file_path, job_id)
        except Exception as e:
            logger.warning("Error parsing file %s for job %s: %s", output_file_path, job_id, e, exc_info=True)

    def _parse_squeue_status(self, job_ids: list[str]) -> dict:
        """Parses the status from squeue output."""
        command = ["squeue", "--jobs=" + ",".join(job_ids), "--noheader", "--format=%i,%T"]
        logger.debug("Running squeue command: %s", " ".join(command))
        squeue_result = subprocess.run(command, capture_output=True, text=True)
        
        if squeue_result.stderr:
            logger.warning("squeue command returned an error:\n%s", squeue_result.stderr)

        logger.debug("squeue stdout:\n%s", squeue_result.stdout)
        
        squeue_statuses = {}
        for line in squeue_result.stdout.strip().splitlines():
            parts = line.split(',')
            if len(parts) == 2:
                job_id, state = parts[0].strip(), parts[1].strip()
                normalized_state = self._normalize_squeue_state(state)
                squeue_statuses[job_id] = normalized_state
                logger.debug("Parsed squeue status for job %s: %s -> %s", job_id, state, normalized_state)
        return squeue_statuses

    def _normalize_squeue_state(self, squeue_state: str) -> str:
        """Normalizes various SQUEUE state strings to a common format."""
        squeue_state = squeue_state.strip()
        if squeue_state == "PENDING":
            return "PENDING"
        if squeue_state == "RUNNING":
            return "RUNNING"
        if squeue_state == "COMPLETED":
            return "COMPLETED"
        if squeue_state == "FAILED":
            return "FAILED"
        if squeue_state == "CANCELLED":
            return "CANCELLED"
        if squeue_state == "TIMEOUT":
            return "TIMEOUT"
        return squeue_state # Fallback for other states

    def _parse_sacct_status(self, job_ids: list[str]) -> dict:
        """Parses the final status from sacct output."""
        command = ["sacct", "--jobs=" + ",".join(job_ids), "--noheader", "--format=JobId,State,ExitCode"]
        logger.debug("Running sacct command: %s", " ".join(command))
        sacct_result = subprocess.run(command, capture_output=True, text=True)

        if sacct_result.stderr:
            logger.warning("sacct command returned an error:\n%s", sacct_result.stderr)
            
        logger.debug("sacct stdout:\n%s", sacct_result.stdout)

        sacct_statuses = {}
        # We only care about the primary job entry, not sub-steps like '.batch'
        for line in sacct_result.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) > 1 and parts[0] in job_ids:
                job_id, state = parts[0].strip(), parts[1].strip()
                normalized_state = self._normalize_sacct_state(state)
                sacct_statuses[job_id] = normalized_state
                logger.debug("Parsed sacct status for job %s: %s -> %s", job_id, state, normalized_state)
        return sacct_statuses

    def _normalize_sacct_state(self, sacct_state: str) -> str:
        """Normalizes various SACCT state strings to a common format."""
        sacct_state = sacct_state.strip()
        if sacct_state == "COMPLETED":
            return "COMPLETED"
        if sacct_state == "FAILED":
            return "FAILED"
        if sacct_state == "CANCELLED":
            return "CANCELLED"
        if sacct_state == "TIMEOUT":
            return "TIMEOUT"
        return sacct_state # Fallback for other states

    def check_and_update_statuses(self, specific_job_id: Optional[str] = None):
        """
        Checks the system scheduler for the current status of tracked jobs
        that are in non-terminal states.
        """
        jobs_to_check = []
        if specific_job_id and specific_job_id in self._jobs:
            jobs_to_check = [specific_job_id]
        else: # Check all non-terminal jobs
            jobs_to_check = [
                job_id for job_id, data in self._jobs.items() 
                if data.get("status") in ["PENDING", "RUNNING"]
            ]

        if not jobs_to_check:
            return

        # Check squeue first for active jobs
        squeue_statuses = self._parse_squeue_status(jobs_to_check)
        
        jobs_not_in_squeue = []
        for job_id in jobs_to_check:
            if job_id in squeue_statuses:
                self.set_status(job_id, squeue_statuses[job_id])
            else:
                jobs_not_in_squeue.append(job_id)
        
        # For jobs no longer in squeue, check sacct for final status
        if jobs_not_in_squeue:
            sacct_statuses = self._parse_sacct_status(jobs_not_in_squeue)
            for job_id, status in sacct_statuses.items():
                self.set_status(job_id, status)
