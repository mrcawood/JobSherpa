import os
import yaml
from typing import Optional

from jobsherpa.kb.models import SystemProfile, ApplicationRecipe, DatasetProfile


def _read_yaml(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def load_system_profile_file(path: str) -> SystemProfile:
    data = _read_yaml(path)
    # Pydantic v2 vs v1
    try:
        return SystemProfile.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        return SystemProfile.parse_obj(data)  # type: ignore[attr-defined]


def load_application_recipe_file(path: str) -> ApplicationRecipe:
    data = _read_yaml(path)
    try:
        return ApplicationRecipe.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        return ApplicationRecipe.parse_obj(data)  # type: ignore[attr-defined]


def load_dataset_profile_file(path: str) -> DatasetProfile:
    data = _read_yaml(path)
    try:
        return DatasetProfile.model_validate(data)  # type: ignore[attr-defined]
    except AttributeError:
        return DatasetProfile.parse_obj(data)  # type: ignore[attr-defined]


def load_system_profile(name: str, base_dir: str = "knowledge_base") -> Optional[SystemProfile]:
    path = os.path.join(base_dir, "system", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    return load_system_profile_file(path)


def load_application_recipe(name: str, base_dir: str = "knowledge_base") -> Optional[ApplicationRecipe]:
    path = os.path.join(base_dir, "applications", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    return load_application_recipe_file(path)


def load_dataset_profile(name: str, base_dir: str = "knowledge_base") -> Optional[DatasetProfile]:
    path = os.path.join(base_dir, "datasets", f"{name}.yaml")
    if not os.path.exists(path):
        return None
    return load_dataset_profile_file(path)


