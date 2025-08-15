from unittest.mock import MagicMock, patch

from jobsherpa.agent.tool_executor import ToolExecutor


def test_tool_executor_dry_run():
    te = ToolExecutor(dry_run=True, tool_dir="tools")
    out = te.execute("echo", ["hi"], workspace="/tmp")
    assert "DRY-RUN" in out
    assert "echo hi" in out


def test_tool_executor_executes_system_command(tmp_path):
    te = ToolExecutor(dry_run=False, tool_dir="tools")
    with patch("subprocess.run", return_value=MagicMock(stdout="ok", returncode=0)) as mock_run:
        out = te.execute("echo", ["hi"], workspace=str(tmp_path))
    assert out == "ok"
    mock_run.assert_called_once()


def test_tool_executor_handles_missing_binary(tmp_path):
    te = ToolExecutor(dry_run=False, tool_dir="tools")
    with patch("subprocess.run", side_effect=FileNotFoundError("missing")):
        out = te.execute("missing_command", [], workspace=str(tmp_path))
    assert "Error executing tool" in out

import pytest
from unittest.mock import patch, MagicMock
from jobsherpa.agent.tool_executor import ToolExecutor

def test_tool_executor_runs_system_command():
    """
    Tests that the ToolExecutor can execute a real system command,
    not just a script from the ./tools/ directory.
    """
    executor = ToolExecutor(dry_run=False)
    
    mock_process = MagicMock()
    mock_process.stdout = "hello"

    with patch("subprocess.run", return_value=mock_process) as mock_subprocess:
        result = executor.execute("echo", ["hello"], workspace="/tmp")

        # Verify that subprocess.run was called with the system command
        mock_subprocess.assert_called_with(
            ["echo", "hello"],
            capture_output=True,
            text=True,
            check=True,
            cwd="/tmp"
        )
        
        # Verify the result is the stdout from the command
        assert result == "hello"
