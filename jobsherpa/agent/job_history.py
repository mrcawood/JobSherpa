import time
import re
import logging
from typing import Optional
import os
import json

logger = logging.getLogger(__name__)

from jobsherpa.agent.scheduler import SchedulerClient, SlurmSchedulerClient


class JobHistory:
    """
    Manages the state of active and completed jobs, with persistence.
    """
    def __init__(self, history_file_path: Optional[str] = None, scheduler_client: Optional[SchedulerClient] = None):
        self.history_file_path = history_file_path
        self._jobs = self._load_state()
        # Use provided scheduler client or default to Slurm
        self.scheduler_client = scheduler_client or SlurmSchedulerClient()

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

    def register_job(self, job_id: str, job_name: str, job_directory: str, output_parser_info: Optional[dict] = None):
        """
        Registers a new job with a default 'PENDING' status.
        """
        if job_id not in self._jobs:
            self._jobs[job_id] = {
                "job_id": job_id, # Also store the ID inside the object
                "job_name": job_name,
                "status": "PENDING",
                "start_time": time.time(),
                "job_directory": job_directory,
                "output_parser": output_parser_info,
                "result": None
            }
            logger.info("Registered new job: %s (%s) in directory: %s", job_id, job_name, job_directory)
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

    def check_job_status(self, job_id: str) -> Optional[str]:
        """Public helper to actively refresh and return the current status for a job."""
        if job_id not in self._jobs:
            return None
        self.check_and_update_statuses(specific_job_id=job_id)
        return self._jobs.get(job_id, {}).get("status")

    def get_job_by_id(self, job_id: str) -> Optional[dict]:
        """Returns all information for a specific job ID."""
        return self._jobs.get(job_id)

    def get_latest_job_id(self) -> Optional[str]:
        """Returns the ID of the most recently submitted job."""
        if not self._jobs:
            return None
        
        # Find the job with the maximum start_time
        latest_job_id = max(self._jobs, key=lambda j: self._jobs[j].get("start_time", 0))
        return latest_job_id

    def get_latest_job(self) -> Optional[dict]:
        """
        Retrieves the entire job dictionary for the most recently submitted job.
        
        Returns:
            A dictionary containing the latest job's information, or None if no
            jobs exist.
        """
        latest_job_id = self.get_latest_job_id()
        if latest_job_id:
            return self.get_job_by_id(latest_job_id)
        return None

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
            logger.warning("Job %s missing parsing info. file=%s dir=%s regex=%s", job_id, relative_output_file, job_directory, bool(regex_pattern))
            return

        # The output file path is now relative to the job's unique directory
        output_file_path = os.path.join(job_directory, relative_output_file)
        
        logger.info("Parsing output file for job %s: %s", job_id, output_file_path)
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
                logger.warning("No match in output file for job %s using regex: %s", job_id, regex_pattern)
        except FileNotFoundError:
            logger.warning("Output file not found for job %s: %s", job_id, output_file_path)
        except Exception as e:
            logger.warning("Error parsing result for job %s from %s: %s", job_id, output_file_path, e, exc_info=True)

    def _parse_squeue_status(self, job_ids: list[str]) -> dict:
        """Fetch active statuses using the scheduler client (squeue equivalent)."""
        statuses = self.scheduler_client.get_active_statuses(job_ids)
        for job_id, state in statuses.items():
            logger.debug("Active status for %s: %s", job_id, state)
        return statuses

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
        """Fetch final statuses using the scheduler client (sacct equivalent)."""
        statuses = self.scheduler_client.get_final_statuses(job_ids)
        for job_id, state in statuses.items():
            logger.debug("Final status for %s: %s", job_id, state)
        return statuses

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

        logger.debug("Checking statuses for jobs: %s", jobs_to_check)
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
            logger.debug("Jobs not in squeue; checking sacct: %s", jobs_not_in_squeue)
            sacct_statuses = self._parse_sacct_status(jobs_not_in_squeue)
            if not sacct_statuses:
                logger.warning("sacct returned no statuses for jobs: %s", jobs_not_in_squeue)
            for job_id, status in sacct_statuses.items():
                self.set_status(job_id, status)

    def try_parse_result(self, job_id: str) -> Optional[str]:
        """
        Attempt to parse the job's result from its output file regardless of status.
        Useful when scheduler status is delayed but output exists.
        """
        if job_id not in self._jobs:
            return None
        logger.debug("Attempting direct parse of result for job %s", job_id)
        self._parse_job_output(job_id)
        return self._jobs.get(job_id, {}).get("result")
