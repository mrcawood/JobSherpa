import os
import yaml

from jobsherpa.kb.loader import (
    load_system_profile_file,
    load_application_recipe_file,
    load_dataset_profile_file,
)


def write_yaml(path: str, data: dict):
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


def test_load_system_profile_file(tmp_path):
    data = {
        "name": "Frontera",
        "scheduler": "slurm",
        "commands": {"submit": "sbatch", "status": "squeue", "history": "sacct"},
        "available_partitions": ["normal"],
    }
    p = tmp_path / "sys.yaml"
    write_yaml(p, data)
    sys = load_system_profile_file(str(p))
    assert sys.name == "Frontera"


def test_load_application_recipe_file(tmp_path):
    data = {
        "name": "wrf",
        "template": "wrf.sh.j2",
        "keywords": ["wrf"],
        "output_parser": {"file": "output/rsl.out.0000", "parser_regex": "(\\d+)"},
    }
    p = tmp_path / "app.yaml"
    write_yaml(p, data)
    app = load_application_recipe_file(str(p))
    assert app.template == "wrf.sh.j2"


def test_load_dataset_profile_file(tmp_path):
    data = {
        "name": "katrina",
        "aliases": ["hurricane katrina"],
        "locations": {"Frontera": "/scratch1/datasets/katrina"},
    }
    p = tmp_path / "ds.yaml"
    write_yaml(p, data)
    ds = load_dataset_profile_file(str(p))
    assert "Frontera" in ds.locations


