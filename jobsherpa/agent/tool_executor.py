import subprocess
import os

class ToolExecutor:
    """
    Executes pre-written tool scripts or system commands.
    """
    def __init__(self, dry_run: bool = False, tool_dir: str = "tools"):
        self.dry_run = dry_run
        self.tool_dir = tool_dir

    def execute(self, tool_name: str, args: list[str], script_content: str | None = None) -> str:
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

        print(f"ToolExecutor received command: {' '.join(command)}")

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
            return result.stdout
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            return f"Error executing tool: {e}"
