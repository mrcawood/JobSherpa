from typing import List

from jobsherpa.kb.models import SystemProfile, ApplicationRecipe


class ModuleClient:
    """
    Minimal helper that computes module environment setup:
    - module_init: system-level preparation commands
    - module_loads: application modules to load
    """

    def __init__(self, system: SystemProfile, app: ApplicationRecipe):
        self.system = system
        self.app = app

    def module_init_commands(self) -> List[str]:
        return list(self.system.module_init or [])

    def module_loads(self) -> List[str]:
        return list(self.app.module_loads or [])


