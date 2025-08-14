import pytest
from ruamel.yaml import YAML
from pydantic import ValidationError

from jobsherpa.config import UserConfig
from jobsherpa.agent.config_manager import ConfigManager

VALID_YAML_CONTENT = """
# My user settings
defaults:
  workspace: /path/to/workspace # My main workspace
  system: vista
  partition: development
"""

INVALID_YAML_CONTENT = """
# Missing workspace
defaults:
  system: vista
"""

@pytest.fixture
def config_file(tmp_path):
    file_path = tmp_path / "user.yaml"
    return file_path

def test_config_manager_loads_valid_config(config_file):
    """
    Tests that the ConfigManager can successfully load and parse a valid
    YAML file into a Pydantic model.
    """
    config_file.write_text(VALID_YAML_CONTENT)
    manager = ConfigManager(config_path=str(config_file))
    
    config = manager.load()
    
    assert isinstance(config, UserConfig)
    assert config.defaults.workspace == "/path/to/workspace"
    assert config.defaults.system == "vista"
    assert config.defaults.partition == "development"

def test_config_manager_rejects_invalid_config(config_file):
    """
    Tests that the ConfigManager raises a Pydantic ValidationError when
    loading a config file with missing required fields.
    """
    config_file.write_text(INVALID_YAML_CONTENT)
    manager = ConfigManager(config_path=str(config_file))
    
    with pytest.raises(ValidationError):
        manager.load()

def test_config_manager_saves_and_preserves_comments(config_file):
    """
    Tests that the ConfigManager can save a modified config object
    back to a file while preserving the original comments and structure.
    """
    config_file.write_text(VALID_YAML_CONTENT)
    manager = ConfigManager(config_path=str(config_file))
    
    # 1. Load, modify, and save
    config = manager.load()
    config.defaults.allocation = "NEW-ALLOC"
    manager.save(config)
    
    # 2. Assert that the file content was updated and comments were preserved
    new_content = config_file.read_text()
    assert "# My user settings" in new_content
    assert "# My main workspace" in new_content
    assert "allocation: NEW-ALLOC" in new_content
