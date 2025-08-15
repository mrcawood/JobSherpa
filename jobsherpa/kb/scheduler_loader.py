import os
import yaml
from typing import Optional

from jobsherpa.kb.models import SchedulerProfile


def load_scheduler_profile(name: str, base_dir: str = "knowledge_base") -> Optional[SchedulerProfile]:
    path = os.path.join(base_dir, "schedulers", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    try:
        return SchedulerProfile.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        return SchedulerProfile.parse_obj(data)  # type: ignore[attr-defined]


