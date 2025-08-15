import pytest

from jobsherpa.kb.models import SystemProfile, SystemCommands, ApplicationRecipe, OutputParser, DatasetProfile, StagingSpec


def test_system_profile_minimal_validates():
    sys = SystemProfile(
        name="Frontera",
        scheduler="slurm",
        commands=SystemCommands(submit="sbatch", status="squeue", history="sacct"),
        available_partitions=["normal", "development"],
        job_requirements=["partition", "allocation"],
        module_init=["ml use /scratch1/hpc_tools", "ml benchpro"],
        filesystem_roots={"scratch": "/scratch1", "work": "/work2"},
    )
    assert sys.commands.submit == "sbatch"


def test_application_recipe_with_parser():
    app = ApplicationRecipe(
        name="wrf",
        template="wrf.sh.j2",
        keywords=["wrf", "weather"],
        module_loads=["intel/19", "impi/19"],
        output_parser=OutputParser(file="output/rsl.out.0000", parser_regex=r"(\\d+)"),
    )
    assert app.output_parser is not None


def test_dataset_profile_locations_and_staging():
    ds = DatasetProfile(
        name="katrina",
        aliases=["hurricane katrina"],
        locations={"Frontera": "/scratch1/datasets/katrina"},
        staging=StagingSpec(url="https://example.com/katrina.tgz", steps=["tar xzf katrina.tgz"]),
        pre_run_edits=["sed -i 's/run_hours.*/run_hours=6/' namelist.input"],
        resource_hints={"nodes": 4, "time": "02:00:00"},
    )
    assert "Frontera" in ds.locations


