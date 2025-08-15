import json
import os
from typing import Optional


class AppRegistry:
    """Stores per-system, per-application overrides (e.g., exe_path, module).

    File format (JSON):
    {
      "system_name": {
        "wrf": {"exe_path": "/path/to/wrf.exe", "module": "..."}
      }
    }
    """

    def __init__(self, registry_path: str):
        self.registry_path = registry_path
        self._data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.registry_path):
            try:
                with open(self.registry_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def get_exe_path(self, system_name: str, app_name: str) -> Optional[str]:
        return (
            self._data.get(system_name, {}).get(app_name, {}).get("exe_path")
        )

    def set_exe_path(self, system_name: str, app_name: str, exe_path: str) -> None:
        self._data.setdefault(system_name, {}).setdefault(app_name, {})["exe_path"] = exe_path
        self.save()


