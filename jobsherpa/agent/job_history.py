import threading
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
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self.cycle_done_event = threading.Event()

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
        Retrieves the status of a specific job.
        """
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

    def _parse_squeue_status(self, squeue_output: str, job_id: str) -> Optional[str]:
        """Parses the status from squeue output."""
        if not squeue_output:
            return None

        # Normalize any escaped newlines ("\\n") to real newlines to handle mocked outputs
        normalized_output = squeue_output.replace("\\n", "\n").strip()
        lines = normalized_output.splitlines()

        # Skip header (first line) and iterate over potential job rows
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split()
            if parts and parts[0] == job_id:
                # Be robust to varying column layouts. Search for a known short SLURM state token.
                known_running = {"R", "CG"}
                known_pending = {"PD"}

                # Search tokens (excluding job_id) for a known state
                for token in parts[1:]:
                    if token in known_running:
                        return "RUNNING"
                    if token in known_pending:
                        return "PENDING"
                # Other states like F, CA, TO etc. mean it's finished but we wait for sacct
        return None  # Not found in squeue, might be completed

    def _parse_sacct_status(self, sacct_output: str, job_id: str) -> Optional[str]:
        """Parses the final status from sacct output."""
        lines = sacct_output.strip().split('\n')
        for line in lines:
            if line.startswith(job_id):
                parts = line.split('|')
                slurm_state = parts[1]
                if slurm_state == "COMPLETED":
                    return "COMPLETED"
                else:
                    return "FAILED" # Treat any other final state as FAILED
        return None # Job not found in sacct, which is strange

    def check_and_update_statuses(self):
        """
        The core logic for checking and updating job statuses by calling SLURM commands.
        """
        for job_id, job_data in list(self._jobs.items()):
            if job_data["status"] in ["PENDING", "RUNNING"]:
                try:
                    squeue_result = subprocess.run(
                        ["squeue", "--job", job_id],
                        capture_output=True,
                        text=True,
                    )
                    logger.debug("squeue output for job %s:\n%s", job_id, squeue_result.stdout)
                    new_status = self._parse_squeue_status(squeue_result.stdout, job_id)
                    
                    if new_status:
                        self.set_status(job_id, new_status)
                    else:
                        # Job not in squeue, check sacct for final status
                        sacct_result = subprocess.run(
                            ["sacct", f"--jobs={job_id}", "--noheader", "--format=JobId,State,ExitCode"],
                            capture_output=True,
                            text=True,
                        )
                        logger.debug("sacct output for job %s:\n%s", job_id, sacct_result.stdout)
                        final_status = self._parse_sacct_status(sacct_result.stdout, job_id)
                        if final_status:
                            self.set_status(job_id, final_status)
                except FileNotFoundError:
                    logger.error("SLURM commands (squeue, sacct) not found. Cannot check job status.")
                    break

    def _monitor_loop(self):
        """The main loop for the monitoring thread."""
        while not self._stop_event.is_set():
            self.check_and_update_statuses()
            self._stop_event.wait(1)

    def start_monitoring(self):
        """Starts the background monitoring thread."""
        if not self._monitor_thread:
            self.cycle_done_event.clear()
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

    def stop_monitoring(self):
        """Stops the background monitoring thread."""
        if self._monitor_thread:
            self._stop_event.set()
            # No need to join, as it's a daemon thread that will exit.
            # In a real app, we might want a more graceful shutdown.
            self._monitor_thread = None
