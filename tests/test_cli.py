import pytest
from typer.testing import CliRunner
import yaml
import os

from jobsherpa.cli.main import app # We need to import the app object

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
