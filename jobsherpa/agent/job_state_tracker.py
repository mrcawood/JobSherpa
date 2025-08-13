import threading
import time
import subprocess
import re

class JobStateTracker:
    """
    Manages the state of active and completed jobs.
    """
    def __init__(self):
        """Initializes the tracker with an in-memory job store."""
        self._jobs = {}
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self.cycle_done_event = threading.Event()

    def register_job(self, job_id: str, output_parser_info: dict | None = None):
        """
        Registers a new job with a default 'PENDING' status.
        """
        if job_id not in self._jobs:
            self._jobs[job_id] = {
                "status": "PENDING",
                "start_time": time.time(),
                "output_parser": output_parser_info,
                "result": None
            }

    def get_status(self, job_id: str) -> str | None:
        """
        Retrieves the status of a specific job.
        """
        return self._jobs.get(job_id, {}).get("status")

    def set_status(self, job_id: str, status: str):
        """
        Updates the status of a specific job.
        """
        if job_id in self._jobs:
            self._jobs[job_id]["status"] = status
            if status == "COMPLETED" and self._jobs[job_id]["output_parser"]:
                self._parse_job_output(job_id)
    
    def get_result(self, job_id: str) -> str | None:
        """Gets the parsed result of a completed job."""
        return self._jobs.get(job_id, {}).get("result")

    def _parse_job_output(self, job_id: str):
        """Parses the output file of a completed job to find a result."""
        job_info = self._jobs.get(job_id)
        if not job_info or not job_info.get("output_parser"):
            return

        parser_info = job_info["output_parser"]
        output_file = parser_info.get("file")
        regex = parser_info.get("parser_regex")

        if not output_file or not regex:
            return

        try:
            with open(output_file, 'r') as f:
                content = f.read()
            
            match = re.search(regex, content)
            if match:
                self._jobs[job_id]["result"] = match.group(1)
        except FileNotFoundError:
            print(f"Warning: Could not find output file {output_file} to parse for job {job_id}.")
        except Exception as e:
            print(f"Warning: Error parsing file {output_file} for job {job_id}: {e}")

    def _parse_squeue_status(self, squeue_output: str, job_id: str) -> str | None:
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

    def _parse_sacct_status(self, sacct_output: str, job_id: str) -> str | None:
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
                        final_status = self._parse_sacct_status(sacct_result.stdout, job_id)
                        if final_status:
                            self.set_status(job_id, final_status)
                except FileNotFoundError:
                    print("Warning: SLURM commands not found. Cannot check job status.")
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
