from jobsherpa.kb.site_loader import load_site_profile


def test_load_site_profile(tmp_path):
    site_dir = tmp_path / "kb" / "site"
    site_dir.mkdir(parents=True)
    (site_dir / "TACC.yaml").write_text(
        """
name: TACC
job_requirements: [partition, allocation]
module_init: [ml use /site/modulefiles]
        """.strip()
    )
    prof = load_site_profile("TACC", base_dir=str(tmp_path / "kb"))
    assert prof is not None and "partition" in prof.job_requirements


