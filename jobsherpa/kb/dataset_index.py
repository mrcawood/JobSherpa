import os
import yaml
from typing import Dict, Optional

from jobsherpa.kb.models import DatasetProfile


class DatasetIndex:
    def __init__(self, base_dir: str = "knowledge_base"):
        self.base_dir = base_dir
        self._name_to_profile: Dict[str, DatasetProfile] = {}
        self._alias_to_name: Dict[str, str] = {}

    def index(self) -> None:
        datasets_dir = os.path.join(self.base_dir, "datasets")
        if not os.path.isdir(datasets_dir):
            return
        for filename in os.listdir(datasets_dir):
            if filename.endswith(".yaml"):
                path = os.path.join(datasets_dir, filename)
                try:
                    with open(path, "r") as f:
                        data = yaml.safe_load(f) or {}
                    try:
                        profile = DatasetProfile.model_validate(data)  # type: ignore[attr-defined]
                    except AttributeError:
                        profile = DatasetProfile.parse_obj(data)  # type: ignore[attr-defined]
                except Exception:
                    # Skip invalid or unreadable dataset profiles
                    continue
                self._name_to_profile[profile.name.lower()] = profile
                for alias in [profile.name] + profile.aliases:
                    self._alias_to_name[alias.lower()] = profile.name.lower()

    def resolve(self, text: str) -> Optional[DatasetProfile]:
        """Find a dataset by name or alias appearing in free text."""
        text_l = text.lower()
        for alias, canonical in self._alias_to_name.items():
            if alias in text_l:
                return self._name_to_profile.get(canonical)
        return None


