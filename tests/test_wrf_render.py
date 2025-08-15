import os
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
import yaml

from jobsherpa.kb.loader import load_system_profile_file, load_application_recipe_file, load_dataset_profile_file


def test_wrf_script_renders_header_and_launcher(tmp_path):
    # Load KB files
    repo_root = Path(__file__).resolve().parents[1]
    sys = load_system_profile_file(str(repo_root / "knowledge_base/system/frontera.yaml"))
    app = load_application_recipe_file(str(repo_root / "knowledge_base/applications/wrf.yaml"))
    ds = load_dataset_profile_file(str(repo_root / "knowledge_base/datasets/katrina.yaml"))

    # Compose minimal context
    job_dir = tmp_path / "wrf_job"
    os.makedirs(job_dir / "slurm", exist_ok=True)
    context = {
        "job_name": "wrf-katrina",
        "partition": sys.available_partitions[0],
        "allocation": "A-ccsc",
        "nodes": 1,
        "ntasks_per_node": 56,
        "time": "01:00:00",
        "module_init": sys.module_init,
        "module_loads": app.module_loads,
        "launcher": sys.commands.launcher or "srun",
        "wrf_exe": "wrf.exe",
        "job_dir": str(job_dir),
    }

    env = Environment(loader=FileSystemLoader(str(repo_root / "tools")))
    template = env.get_template(app.template)
    rendered = template.render(context)

    assert "#SBATCH --partition" in rendered
    assert "#SBATCH --nodes=1" in rendered
    assert "ibrun" in rendered or "srun" in rendered


