import pytest
from unittest.mock import MagicMock, patch
from freezegun import freeze_time
import time

from jobsherpa.agent.job_history import JobHistory
from jobsherpa.agent.scheduler import SchedulerClient

class MockScheduler(SchedulerClient):
    def __init__(self, active=None, final=None):
        self.active = active or {}
        self.final = final or {}

    def get_active_statuses(self, job_ids):
        return {j: self.active.get(j) for j in job_ids if j in self.active}

    def get_final_statuses(self, job_ids):
        return {j: self.final.get(j) for j in job_ids if j in self.final}


@pytest.fixture
def job_history():
    return JobHistory(scheduler_client=MockScheduler())

def test_register_and_get_status(job_history):
    """
    Tests that a job can be registered and its initial status is 'PENDING'.
    """
    job_id = "mock_12345"
    job_history.register_job("mock_12345", job_name="test_job", job_directory="/tmp/mock_dir")
    # In the new model, get_status will try to check, so we need to mock subprocess
    assert job_history.get_status(job_id) == "PENDING"

def test_set_status(job_history):
    """
    Tests that a job's status can be manually set.
    """
    job_id = "mock_12345"
    job_history.register_job("mock_12345", job_name="test_job", job_directory="/tmp/mock_dir")
    job_history.set_status("mock_12345", "RUNNING")
    assert job_history.get_status(job_id) == "RUNNING"

def test_history_persists_to_file(tmp_path):
    """
    Tests that the JobHistory component can save its state to a file
    and load it back upon re-initialization.
    """
    history_file = tmp_path / "history.json"
    job_id = "mock_123"
    
    # 1. Create the first instance, register a job, and it should save.
    history1 = JobHistory(history_file_path=str(history_file), scheduler_client=MockScheduler())
    history1.register_job("mock_123", job_name="test_job", job_directory="/tmp/mock_dir")
    assert history_file.is_file()
    
    # 2. Create a second instance pointing to the same file.
    history2 = JobHistory(history_file_path=str(history_file), scheduler_client=MockScheduler())
    
    # 3. Assert that the second instance has loaded the state of the first.
    assert history2.get_status(job_id) == "PENDING"

def test_get_status_actively_checks_squeue(job_history):
    """
    Tests that calling get_status on a PENDING job triggers a call
    to squeue and updates the status if the job is found running.
    """
    job_id = "12345"
    job_history.register_job(job_id, job_name="test_job", job_directory="/tmp/mock_dir")

    # Mock squeue showing the job is now running
    # Inject scheduler that reports RUNNING
    job_history.scheduler_client = MockScheduler(active={job_id: "RUNNING"})
    status = job_history.get_status(job_id)
    assert status == "RUNNING"

def test_get_status_actively_checks_sacct(job_history):
    """
    Tests that calling get_status on a RUNNING job triggers a check,
    finds the job is not in squeue, and then finds its final
    COMPLETED status in sacct.
    """
    job_id = "12345"
    job_history.register_job(job_id, job_name="test_job", job_directory="/tmp/mock_dir")
    job_history.set_status(job_id, "RUNNING")

    # Mock squeue returning empty, then sacct returning COMPLETED
    job_history.scheduler_client = MockScheduler(active={}, final={job_id: "COMPLETED"})
    status = job_history.get_status(job_id)
    assert status == "COMPLETED"

def test_get_status_for_completed_job_does_not_recheck(job_history):
    """
    Tests that calling get_status on a job already in a terminal state
    (e.g., COMPLETED) does not trigger a system call.
    """
    job_id = "12345"
    job_history.register_job(job_id, job_name="test_job", job_directory="/tmp/mock_dir")
    job_history.set_status(job_id, "COMPLETED")
    
    status = job_history.get_status(job_id)
    assert status == "COMPLETED"

@freeze_time("2025-08-14 12:00:00")
def test_history_parses_output_on_completion(job_history, tmp_path):
    """
    Tests that when a job's status is set to COMPLETED, the tracker
    automatically calls the output parser if one is defined.
    """
    job_id = "12345"
    job_dir = tmp_path / "job_dir"
    output_dir = job_dir / "output"
    output_dir.mkdir(parents=True)
    output_file = output_dir / "results.txt"
    with open(output_file, "w") as f:
        f.write("The final value is: 42")
        
    output_parser_info = {
        "file": "output/results.txt",
        "parser_regex": r"value is: (\d+)"
    }
    job_history.register_job(job_id, job_name="test_job", job_directory=str(job_dir), output_parser_info=output_parser_info)
    
    # Act: Manually set status to completed to trigger parsing
    job_history.set_status(job_id, "COMPLETED")
    
    assert job_history.get_result(job_id) == "42"

def test_history_handles_corrupted_file_gracefully(tmp_path):
    """
    Tests that if the history file is corrupted or not valid JSON,
    the JobHistory instance initializes with an empty state.
    """
    history_file = tmp_path / "history.json"
    with open(history_file, "w") as f:
        f.write("this is not valid json")

    history = JobHistory(history_file_path=str(history_file))

    assert history.get_all_jobs() == {}
    history.register_job("123", job_name="test_job", job_directory="/tmp/dir")
    assert "123" in history.get_all_jobs()

def test_parse_job_output_handles_missing_file(job_history, tmp_path):
    """
    Tests that if a job is completed but its output file is missing,
    the result is gracefully set to None.
    """
    job_id = "12345"
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    
    output_parser_info = {
        "file": "output/results.txt",
        "parser_regex": "Value: (\\d+)"
    }
    
    job_history.register_job(job_id, job_name="test_job", job_directory=str(job_dir), output_parser_info=output_parser_info)
    
    # The output file output/results.txt is *not* created.
    job_history.set_status(job_id, "COMPLETED")
    
    assert job_history.get_result(job_id) is None
    assert job_history.get_status(job_id) == "COMPLETED"
