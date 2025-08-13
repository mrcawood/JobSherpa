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
        result = executor.execute("echo", ["hello"])

        # Verify that subprocess.run was called with the system command
        mock_subprocess.assert_called_with(
            ["echo", "hello"],
            capture_output=True,
            text=True,
            check=True,
            input=None
        )
        
        # Verify the result is the stdout from the command
        assert result == "hello"
