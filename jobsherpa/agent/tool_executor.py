import subprocess
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class ToolExecutor:
    """
    Executes pre-written tool scripts or system commands.
    """
    def __init__(self, dry_run: bool = False, tool_dir: str = "tools"):
        self.dry_run = dry_run
        self.tool_dir = tool_dir

    def execute(self, tool_name: str, args: list[str], workspace: Optional[str] = None) -> str:
        """
        Executes a given tool with arguments from within the specified workspace.
        It first checks for a local tool in the tool_dir, otherwise
        assumes it's a system command.
        """
        local_tool_path = os.path.join(self.tool_dir, tool_name)
        
        if os.path.exists(local_tool_path):
            command = [local_tool_path] + args
        else:
            command = [tool_name] + args

        logger.debug("Executing command: %s in workspace: %s", " ".join(command), workspace)

        if self.dry_run:
            return f"DRY-RUN: Would execute: {' '.join(command)} in workspace: {workspace}"
        
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True,
                cwd=workspace
            )
            logger.debug("Command successful. stdout: %s", result.stdout)
            return result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(
                "Error executing tool '%s'. Return code: %s\n---STDOUT---\n%s\n---STDERR---\n%s",
                " ".join(command), e.returncode, e.stdout, e.stderr
            )
            return f"Error executing tool: {e}"
        except FileNotFoundError as e:
            logger.error("Error executing tool '%s'. File not found.", " ".join(command))
            # Friendly message when scheduler CLI is missing locally
            if command and command[0] in {"sbatch", "squeue", "sacct", "scancel"}:
                return (
                    f"Scheduler command '{command[0]}' not found on this host. "
                    f"Run this job on your HPC login node or use --dry-run locally."
                )
            return f"Error executing tool: {e}"
