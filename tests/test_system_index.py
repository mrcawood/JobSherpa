from jobsherpa.kb.system_index import SystemIndex


def test_system_index_resolves_system_by_name(tmp_path):
    sys_dir = tmp_path / "kb" / "system"
    sys_dir.mkdir(parents=True)
    (sys_dir / "frontera.yaml").write_text(
        """
name: Frontera
scheduler: slurm
commands: {submit: sbatch, status: squeue, history: sacct}
        """.strip()
    )
    idx = SystemIndex(base_dir=str(tmp_path / "kb"))
    idx.index()
    prof = idx.resolve("run WRF on Frontera please")
    assert prof is not None and prof.name == "Frontera"


