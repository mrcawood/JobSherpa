from jobsherpa.kb.dataset_index import DatasetIndex


def test_dataset_index_resolves_alias(tmp_path, monkeypatch):
    # Create a minimal datasets dir
    ds_dir = tmp_path / "kb" / "datasets"
    ds_dir.mkdir(parents=True)
    (ds_dir / "katrina.yaml").write_text(
        """
name: katrina
aliases: ["hurricane katrina"]
locations: {Frontera: /scratch1/datasets/katrina}
        """.strip()
    )
    idx = DatasetIndex(base_dir=str(tmp_path / "kb"))
    idx.index()

    prof = idx.resolve("Run a WRF simulation of hurricane katrina on Frontera")
    assert prof is not None and prof.name == "katrina"


