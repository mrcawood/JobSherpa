import pytest
from typer.testing import CliRunner
import yaml
import os

from jobsherpa.cli.main import app # We need to import the app object
from unittest.mock import patch, MagicMock
import getpass
import jinja2

runner = CliRunner()

def test_config_set_and_get(tmp_path):
    """
    Tests that we can set a configuration value and then get it back.
    """
    user_profile_dir = tmp_path / "user"
    user_profile_dir.mkdir()
    user_profile_file = user_profile_dir / "test_user.yaml"

    # 1. Set a value
    result_set = runner.invoke(
        app,
        [
            "config",
            "set",
            "workspace",
            "/path/to/my/workspace",
            "--user-profile-path", # Use a direct path for testing
            str(user_profile_file),
        ],
    )
    assert result_set.exit_code == 0
    assert "Updated configuration" in result_set.stdout

    # Verify the file content
    with open(user_profile_file, 'r') as f:
        config = yaml.safe_load(f)
    assert config["defaults"]["workspace"] == "/path/to/my/workspace"

    # 2. Get the value back
    result_get = runner.invoke(
        app,
        [
            "config",
            "get",
            "workspace",
            "--user-profile-path",
            str(user_profile_file),
        ],
    )
    assert result_get.exit_code == 0
    assert "/path/to/my/workspace" in result_get.stdout


def test_config_uses_current_user_as_default(tmp_path):
    """
    Tests that the config command defaults to using the current system
    user's profile if --user-profile is not provided.
    """
    # 1. Set up a dummy knowledge base and user profile in a temporary directory
    kb_path = tmp_path / "knowledge_base"
    user_dir = kb_path / "user"
    user_dir.mkdir(parents=True)
    
    test_user = "testuser"
    user_profile_file = user_dir / f"{test_user}.yaml"
    user_profile = {"defaults": {"partition": "test-partition"}}
    with open(user_profile_file, 'w') as f:
        yaml.dump(user_profile, f)

    # 2. Mock getpass.getuser() to return our predictable test username
    # and change the current directory to our temp dir so the relative path works.
    with patch("getpass.getuser", return_value=test_user):
        os.chdir(tmp_path)
        result = runner.invoke(app, ["config", "get", "partition"])

    # 3. Assert that the command succeeded and returned the correct value
    assert result.exit_code == 0
    assert "test-partition" in result.stdout


def test_config_show(tmp_path):
    """
    Tests that `config show` prints the entire user configuration.
    """
    # 1. Setup: Create a dummy user profile file.
    kb_path = tmp_path / "knowledge_base"
    user_dir = kb_path / "user"
    user_dir.mkdir(parents=True)

    test_user = "testuser"
    user_profile_file = user_dir / f"{test_user}.yaml"
    user_profile = {
        "defaults": {
            "partition": "test-partition",
            "allocation": "TEST-123"
        },
        "contact": "test@example.com"
    }
    with open(user_profile_file, 'w') as f:
        yaml.dump(user_profile, f)

    # 2. Act: Run the `config show` command, passing a direct path to the profile.
    result = runner.invoke(
        app,
        [
            "config",
            "show",
            "--user-profile-path",
            str(user_profile_file)
        ]
    )

    # 3. Assert: Check for successful exit and correct, formatted output.
    assert result.exit_code == 0
    output = result.stdout
    assert "defaults" in output
    assert "partition: test-partition" in output
    assert "allocation: TEST-123" in output
    assert "contact: test@example.com" in output


def test_config_show_no_file(tmp_path):
    """
    Tests that `config show` shows a user-friendly message when the
    profile file does not exist.
    """
    test_user = "ghostuser"
    
    # We can test the error message without mocking getuser by providing a bad path
    bad_path = tmp_path / "non_existent_profile.yaml"
    result = runner.invoke(app, ["config", "show", "--user-profile-path", str(bad_path)])

    assert result.exit_code != 0
    assert "User profile not found" in result.stdout
    assert "non_existent_profile.yaml" in result.stdout


@patch("jobsherpa.agent.agent.JobSherpaAgent._find_matching_recipe")
@patch("jobsherpa.agent.tool_executor.ToolExecutor.execute")
def test_run_command_defaults_to_current_user(mock_execute, mock_find_recipe, tmp_path):
    """
    Tests that the `run` command, when called without --user-profile,
    defaults to the current user's config and correctly sets up the workspace.
    """
    # 1. Setup: Create a workspace and a user profile file for a test user
    workspace_path = tmp_path / "test_workspace"
    workspace_path.mkdir()
    
    # The CLI will look for knowledge_base relative to the current directory
    kb_path = tmp_path / "knowledge_base"
    user_dir = kb_path / "user"
    user_dir.mkdir(parents=True)
    system_dir = kb_path / "system" # Needed for system config
    system_dir.mkdir(parents=True)
    
    # The agent will look for a tools directory for the template
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "mock.j2").touch()


    # Create a dummy system profile to avoid other errors
    with open(system_dir / "vista.yaml", "w") as f:
        yaml.dump({"name": "vista"}, f)

    test_user = "testuser"
    user_profile_file = user_dir / f"{test_user}.yaml"
    user_profile = {
        "defaults": {
            "workspace": str(workspace_path),
            "partition": "test-partition",
            "allocation": "TEST-123",
            "system": "vista", # Required for the agent
        }
    }
    with open(user_profile_file, 'w') as f:
        yaml.dump(user_profile, f)

    # Mock the agent's recipe finding and execution logic
    mock_find_recipe.return_value = {
        "name": "mock_recipe", "template": "mock.j2", "tool": "sbatch"
    }
    mock_execute.return_value = "Submitted batch job mock_789"

    # 2. Act: Run the `run` command, mocking the user and changing the CWD
    with patch("getpass.getuser", return_value=test_user), \
         patch("jinja2.FileSystemLoader", return_value=jinja2.FileSystemLoader(str(tools_dir))):
        
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            # Note: We no longer need --system-profile, as it's in the user's config
            result = runner.invoke(app, ["run", "Do something"])
        finally:
            os.chdir(original_cwd)

    # 3. Assert
    assert result.exit_code == 0, f"CLI command failed with output: {result.stdout}"
    assert "Job submitted successfully" in result.stdout
    
    # Verify the workspace was correctly used
    mock_execute.assert_called_once()
    call_kwargs = mock_execute.call_args.kwargs
    assert call_kwargs.get("workspace") == str(workspace_path)
