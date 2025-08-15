from unittest.mock import MagicMock, patch

from jobsherpa.agent.scheduler import SlurmSchedulerClient


def test_slurm_get_active_statuses_parses_squeue_output():
    client = SlurmSchedulerClient()
    fake_stdout = "\n".join([
        "111,RUNNING",
        "222,PENDING",
    ])
    with patch("subprocess.run", return_value=MagicMock(stdout=fake_stdout, stderr="")) as mock_run:
        statuses = client.get_active_statuses(["111", "222", "333"])  # 333 not present
    assert statuses == {"111": "RUNNING", "222": "PENDING"}


def test_slurm_get_final_statuses_parses_sacct_output():
    client = SlurmSchedulerClient()
    # Simulate sacct output lines; spacing is flexible
    fake_stdout = "\n".join([
        "111      COMPLETED      0:0",
        "111.batch COMPLETED      0:0",
        "222      FAILED         1:0",
    ])
    with patch("subprocess.run", return_value=MagicMock(stdout=fake_stdout, stderr="")) as mock_run:
        statuses = client.get_final_statuses(["111", "222", "333"])  # 333 not present
    assert statuses == {"111": "COMPLETED", "222": "FAILED"}


