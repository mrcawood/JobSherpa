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

    def execute(self, tool_name: str, args: list[str], script_content: Optional[str] = None) -> str:
        """
        Executes a given tool with arguments.
        It first checks for a local tool in the tool_dir, otherwise
        assumes it's a system command.
        If script_content is provided, it is passed as stdin to the command.
        """
        local_tool_path = os.path.join(self.tool_dir, tool_name)
        
        if os.path.exists(local_tool_path):
            command = [local_tool_path] + args
        else:
            command = [tool_name] + args

        logger.debug("Executing command: %s", " ".join(command))
        if script_content:
            logger.debug("Passing stdin to command:\n%s", script_content)

        if self.dry_run:
            if script_content:
                return f"DRY-RUN: Would execute: {' '.join(command)} with stdin:\n{script_content}"
            return f"DRY-RUN: Would execute: {' '.join(command)}"
        
        try:
            result = subprocess.run(
                command, 
                capture_output=True, 
                text=True, 
                check=True,
                input=script_content
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
            return f"Error executing tool: {e}"
