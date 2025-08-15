import os
import yaml
from typing import Optional

from jobsherpa.kb.models import SiteProfile
from jobsherpa.kb.loader import load_system_profile


def load_site_profile(name: str, base_dir: str = "knowledge_base") -> Optional[SiteProfile]:
    path = os.path.join(base_dir, "site", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}
    try:
        return SiteProfile.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        return SiteProfile.parse_obj(data)  # type: ignore[attr-defined]


def load_site_with_systems(name: str, base_dir: str = "knowledge_base") -> tuple[Optional[SiteProfile], list]:
    site = load_site_profile(name, base_dir)
    systems = []
    if site:
        for sys_name in site.systems:
            sys_prof = load_system_profile(sys_name, base_dir)
            if sys_prof:
                systems.append(sys_prof)
    return site, systems


