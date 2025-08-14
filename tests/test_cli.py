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
    assert "Updated 'workspace' in profile" in result_set.stdout

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


@patch("jobsherpa.agent.agent.JobSherpaAgent")
def test_run_command_defaults_to_current_user(mock_agent_class, tmp_path):
    """
    Tests that the `run` command correctly initializes the agent and that
    the agent, in turn, calls the appropriate action handler.
    """
    # 1. Setup
    workspace_path = tmp_path / "test_workspace"
    workspace_path.mkdir()
    kb_path = tmp_path / "knowledge_base"
    user_dir = kb_path / "user"
    user_dir.mkdir(parents=True)
    system_dir = kb_path / "system"
    system_dir.mkdir(parents=True)
    with open(system_dir / "vista.yaml", "w") as f:
        yaml.dump({"name": "vista"}, f)
    
    test_user = "testuser"
    user_profile_file = user_dir / f"{test_user}.yaml"
    user_profile = {"defaults": {"workspace": str(workspace_path), "system": "vista"}}
    with open(user_profile_file, 'w') as f:
        yaml.dump(user_profile, f)

    mock_action_instance = mock_agent_class.return_value
    mock_action_instance.run.return_value = ("Job submitted: 12345", "12345", False)

    # 2. Act
    with patch("getpass.getuser", return_value=test_user):
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        result = runner.invoke(app, ["run", "Do something"])
        os.chdir(original_cwd)
    
    # 3. Assert
    assert result.exit_code == 0, f"CLI command failed: {result.stdout}"
    assert "Job submitted: 12345" in result.stdout
    mock_action_instance.run.assert_called_once_with("Do something")


def test_config_set_preserves_comments(tmp_path):
    """
    Tests that `jobsherpa config set` uses the new ConfigManager
    to update a value while preserving existing comments in the YAML file.
    """
    # 1. Setup
    profile_dir = tmp_path / "knowledge_base" / "user"
    profile_dir.mkdir(parents=True)
    profile_file = profile_dir / "testuser.yaml"
    
    initial_content = (
        "# Main user settings\n"
        "defaults:\n"
        "  # The most important setting\n"
        "  workspace: /old/path\n"
    )
    profile_file.write_text(initial_content)

    # 2. Act
    with patch("getpass.getuser", return_value="testuser"):
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        result = runner.invoke(app, ["config", "set", "workspace", "/new/path"])
        os.chdir(original_cwd)

    # 3. Assert
    assert result.exit_code == 0
    
    final_content = profile_file.read_text()
    assert "# Main user settings" in final_content
    assert "# The most important setting" in final_content
    assert "workspace: /new/path" in final_content
    assert "/old/path" not in final_content
