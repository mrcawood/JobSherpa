from jobsherpa.kb.models import SystemProfile, SystemCommands, ApplicationRecipe
from jobsherpa.kb.module_client import ModuleClient


def test_module_client_returns_init_and_loads():
    sys = SystemProfile(
        name="F",
        scheduler="slurm",
        commands=SystemCommands(submit="sbatch", status="squeue", history="sacct"),
        module_init=["ml use /site/modulefiles", "ml benchpro"],
    )
    app = ApplicationRecipe(name="wrf", template="wrf.sh.j2", module_loads=["intel/19", "impi/19"])
    mc = ModuleClient(system=sys, app=app)
    assert mc.module_init_commands() == ["ml use /site/modulefiles", "ml benchpro"]
    assert mc.module_loads() == ["intel/19", "impi/19"]


