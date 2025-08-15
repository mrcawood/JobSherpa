import os
from unittest.mock import patch

import pytest

from jobsherpa.agent.config_manager import ConfigManager
import jobsherpa.agent.config_manager as cm
from jobsherpa.config import UserConfig as BaseUserConfig, UserConfigDefaults


def write_yaml(path: str, content: str):
    with open(path, "w") as f:
        f.write(content)


def test_load_uses_model_validate_when_available(tmp_path, monkeypatch):
    cfg_path = tmp_path / "user.yaml"
    write_yaml(
        cfg_path,
        """
defaults:
  workspace: /tmp
  system: test
        """.strip(),
    )

    # Ensure model_validate path is taken by capturing a call and returning a config
    calls = {"used": False}
    def fake_model_validate(cls, data):
        calls["used"] = True
        return BaseUserConfig(defaults=UserConfigDefaults(**data["defaults"]))
    monkeypatch.setattr(cm.UserConfig, "model_validate", classmethod(fake_model_validate), raising=False)

    manager = ConfigManager(config_path=str(cfg_path))
    loaded = manager.load()
    assert isinstance(loaded, BaseUserConfig)
    assert loaded.defaults.workspace == "/tmp"
    assert loaded.defaults.system == "test"
    assert calls["used"] is True


def test_save_uses_model_dump_when_available(tmp_path, monkeypatch):
    cfg_path = tmp_path / "user.yaml"
    # Pre-existing file to preserve structure/comments (not strictly required here)
    write_yaml(cfg_path, "defaults: {workspace: /old, system: old}")

    class Dummy:
        def model_dump(self, exclude_none=True):
            return {"defaults": {"workspace": "/new", "system": "new"}}

    manager = ConfigManager(config_path=str(cfg_path))
    manager.save(Dummy())

    # Verify file content reflects model_dump output
    with open(cfg_path, "r") as f:
        text = f.read()
    assert "workspace" in text and "/new" in text
    assert "system" in text and "new" in text


def test_save_falls_back_to_dict_if_no_model_dump(tmp_path):
    cfg_path = tmp_path / "user.yaml"
    write_yaml(cfg_path, "defaults: {workspace: /old, system: old}")

    base = BaseUserConfig(defaults=UserConfigDefaults(workspace="/from_dict", system="sys"))

    manager = ConfigManager(config_path=str(cfg_path))
    manager.save(base)

    with open(cfg_path, "r") as f:
        text = f.read()
    assert "/from_dict" in text
    assert "sys" in text

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
