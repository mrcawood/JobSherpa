import pytest
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from jobsherpa.agent.job_history import JobHistory
import json

@pytest.fixture
def job_history():
    return JobHistory()

def test_register_and_get_status(job_history):
    """
    Tests that a job can be registered with the tracker and
    its initial status is 'PENDING'.
    """
    job_id = "mock_12345"
    job_history.register_job(job_id, "/tmp/mock_dir")
    assert job_history.get_status(job_id) == "PENDING"


def test_update_status(job_history):
    """
    Tests that a job's status can be updated.
    """
    job_id = "mock_12345"
    job_history.register_job(job_id, "/tmp/mock_dir")
    job_history.set_status(job_id, "RUNNING")
    assert job_history.get_status(job_id) == "RUNNING"


def test_update_from_squeue_output(job_history):
    """
    Tests that the tracker can parse squeue output to update job status.
    """
    job_id = "12345"
    job_history.register_job(job_id, "/tmp/mock_dir")

    mock_squeue_running = MagicMock()
    mock_squeue_running.stdout = (
        "JOBID PARTITION NAME USER ST TIME NODES NODELIST(REASON)\n"
        f"{job_id} debug hello_world user R 0:01 1 node01"
    )
    
    with patch("subprocess.run", return_value=mock_squeue_running) as mock_subprocess:
        job_history.check_and_update_statuses()
        mock_subprocess.assert_called_with(["squeue", "--job", job_id], capture_output=True, text=True)
        assert job_history.get_status(job_id) == "RUNNING"

def test_update_from_sacct_output_completed(job_history):
    """
    Tests that the tracker calls sacct when a job is not in squeue
    and correctly parses the 'COMPLETED' status.
    """
    job_id = "12345"
    job_history.register_job(job_id, "/tmp/mock_dir")
    job_history.set_status(job_id, "RUNNING") # Assume job was running

    mock_squeue_empty = MagicMock(stdout="") # squeue shows the job is done
    mock_sacct_completed = MagicMock(
        stdout=f"{job_id}|COMPLETED|0:0"
    )

    # Mock squeue returning empty, then sacct returning COMPLETED
    with patch("subprocess.run", side_effect=[mock_squeue_empty, mock_sacct_completed]) as mock_subprocess:
        job_history.check_and_update_statuses()

        # Verify that sacct was called with the correct format
        sacct_call = mock_subprocess.call_args_list[1]
        assert "sacct" in sacct_call.args[0]
        assert f"--jobs={job_id}" in sacct_call.args[0]
        
        # Verify the final status is COMPLETED
        assert job_history.get_status(job_id) == "COMPLETED"

def test_history_persists_to_file(tmp_path):
    """
    Tests that the JobHistory component can save its state to a file
    and load it back upon re-initialization.
    """
    history_file = tmp_path / "history.json"
    job_id = "mock_123"

    # 1. Create the first instance, register a job, and it should save.
    history1 = JobHistory(history_file_path=str(history_file))
    history1.register_job(job_id, "/tmp/mock_dir")

    # Verify the file was written
    assert history_file.is_file()

    # 2. Create a second instance pointing to the same file.
    history2 = JobHistory(history_file_path=str(history_file))
    
    # 3. Assert that the second instance has loaded the state of the first.
    assert history2.get_status(job_id) == "PENDING"

def test_history_loads_from_existing_file(tmp_path):
    """
    Tests that the JobHistory component can save its state to a file
    and load it back upon re-initialization.
    """
    history_file = tmp_path / "history.json"
    job_id = "mock_123"

    # 1. Create the first instance, register a job, and it should save.
    history1 = JobHistory(history_file_path=str(history_file))
    history1.register_job(job_id, "/tmp/mock_dir")

    # Verify the file was written
    assert history_file.is_file()

    # 2. Create a second instance pointing to the same file.
    history2 = JobHistory(history_file_path=str(history_file))
    
    # 3. Assert that the second instance has loaded the state of the first.
    assert history2.get_status(job_id) == "PENDING"

def test_history_handles_corrupted_file_gracefully(tmp_path):
    """
    Tests that if the history file is corrupted or not valid JSON,
    the JobHistory instance initializes with an empty state.
    """
    # 1. Setup
    history_file = tmp_path / "history.json"
    with open(history_file, "w") as f:
        f.write("this is not valid json")

    # 2. Act
    history = JobHistory(history_file_path=str(history_file))

    # 3. Assert
    assert history._jobs == {}
    # Verify we can still add a new job
    history.register_job("123", "/tmp/dir")
    assert "123" in history._jobs

def test_parse_job_output_handles_missing_file(job_history, tmp_path):
    """
    Tests that if a job is completed but its output file is missing,
    the result is gracefully set to None.
    """
    # 1. Setup
    job_id = "12345"
    job_dir = tmp_path / "job_dir"
    job_dir.mkdir()
    
    output_parser_info = {
        "file": "output/results.txt",
        "parser_regex": "Value: (\\d+)"
    }
    
    job_history.register_job(job_id, str(job_dir), output_parser_info=output_parser_info)
    
    # The output file output/results.txt is *not* created.
    
    # 2. Act
    job_history.set_status(job_id, "COMPLETED")
    
    # 3. Assert
    assert job_history.get_result(job_id) is None
    assert job_history.get_status(job_id) == "COMPLETED"
