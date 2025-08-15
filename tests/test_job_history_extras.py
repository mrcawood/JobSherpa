from pathlib import Path
from unittest.mock import MagicMock

from jobsherpa.agent.job_history import JobHistory


class DummyScheduler:
    def get_active_statuses(self, job_ids):
        return {}

    def get_final_statuses(self, job_ids):
        return {}


def test_try_parse_result_reads_output(tmp_path):
    job_dir = tmp_path / "job"
    out_dir = job_dir / "output"
    out_dir.mkdir(parents=True)
    out_file = out_dir / "rng.txt"
    out_file.write_text("The value is 42\n")

    history = JobHistory(history_file_path=None, scheduler_client=DummyScheduler())
    history.register_job(
        job_id="1",
        job_name="test",
        job_directory=str(job_dir),
        output_parser_info={"file": "output/rng.txt", "parser_regex": r"(\d+)"},
    )
    result = history.try_parse_result("1")
    assert result == "42"


def test_parse_skips_when_parser_info_missing(tmp_path):
    job_dir = tmp_path / "job"
    job_dir.mkdir(parents=True)
    history = JobHistory(history_file_path=None, scheduler_client=DummyScheduler())
    history.register_job(
        job_id="2",
        job_name="test",
        job_directory=str(job_dir),
        output_parser_info=None,
    )
    # Should not raise, should keep result None
    assert history.try_parse_result("2") is None


