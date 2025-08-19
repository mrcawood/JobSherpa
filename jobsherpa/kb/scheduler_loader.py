import os
import yaml
from typing import Optional
import logging

from jobsherpa.kb.models import SchedulerProfile
from jobsherpa.util.io import read_yaml

logger = logging.getLogger(__name__)


def load_scheduler_profile(name: str, base_dir: str = "knowledge_base") -> Optional[SchedulerProfile]:
    path = os.path.join(base_dir, "schedulers", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    data = read_yaml(path)
    try:
        logger.debug("Loading scheduler profile from KB: %s", path)
        return SchedulerProfile.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        logger.debug("Loading scheduler profile from KB (pydantic v1): %s", path)
        return SchedulerProfile.parse_obj(data)  # type: ignore[attr-defined]


