import os
import yaml
from typing import Dict, Optional

from jobsherpa.kb.models import SystemProfile


class SystemIndex:
    def __init__(self, base_dir: str = "knowledge_base"):
        self.base_dir = base_dir
        self._name_to_profile: Dict[str, SystemProfile] = {}

    def index(self) -> None:
        systems_dir = os.path.join(self.base_dir, "system")
        if not os.path.isdir(systems_dir):
            return
        for filename in os.listdir(systems_dir):
            if filename.endswith(".yaml"):
                path = os.path.join(systems_dir, filename)
                try:
                    with open(path, "r") as f:
                        data = yaml.safe_load(f) or {}
                    try:
                        profile = SystemProfile.model_validate(data)  # type: ignore[attr-defined]
                    except AttributeError:
                        profile = SystemProfile.parse_obj(data)  # type: ignore[attr-defined]
                except Exception:
                    # Skip invalid/unreadable files in test/mocked environments
                    continue
                self._name_to_profile[profile.name.lower()] = profile

    def resolve(self, text: str) -> Optional[SystemProfile]:
        text_l = text.lower()
        for name, profile in self._name_to_profile.items():
            if name in text_l:
                return profile
        return None


