from ruamel.yaml import YAML
from jobsherpa.config import UserConfig
import os

class ConfigManager:
    """
    Manages loading, validating, and saving user configuration files
    while preserving comments and formatting.
    """
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    def load(self) -> UserConfig:
        """
        Loads the YAML file, validates it with Pydantic, and returns a
        UserConfig object.
        """
        with open(self.config_path, 'r') as f:
            data = self.yaml.load(f)
        # Pydantic v1 vs v2 compatibility
        try:
            return UserConfig.model_validate(data)  # v2
        except AttributeError:
            return UserConfig.parse_obj(data)  # v1

    def save(self, config: UserConfig):
        """
        Saves a UserConfig object back to the YAML file, preserving comments.
        """
        raw_data = {}
        # If the file exists, load it to preserve comments and structure.
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                raw_data = self.yaml.load(f) or {}
        
        # Convert the Pydantic model to a dictionary for updating.
        # Use exclude_none=True to avoid writing null values for optional fields.
        # Pydantic v1 vs v2 compatibility
        try:
            updated_data = config.model_dump(exclude_none=True)  # v2
        except AttributeError:
            updated_data = config.dict(exclude_none=True)  # v1
        
        # A simple deep merge for the 'defaults' key.
        if 'defaults' not in raw_data:
            raw_data['defaults'] = {}
        raw_data['defaults'].update(updated_data.get('defaults', {}))

        with open(self.config_path, 'w') as f:
            self.yaml.dump(raw_data, f)
