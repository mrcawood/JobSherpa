import os
import yaml

from jobsherpa.agent.recipe_index import SimpleKeywordIndex


def write_yaml(path, data):
    with open(path, "w") as f:
        yaml.safe_dump(data, f)


def test_simple_keyword_index_selects_best(tmp_path):
    kb_dir = tmp_path / "kb"
    apps = kb_dir / "applications"
    apps.mkdir(parents=True)

    write_yaml(apps / "a.yaml", {"name": "A", "keywords": ["alpha", "beta"]})
    write_yaml(apps / "b.yaml", {"name": "B", "keywords": ["gamma", "delta"]})

    idx = SimpleKeywordIndex(str(kb_dir))
    idx.index()

    # Should match A (alpha, beta)
    match = idx.find_best("please run alpha and beta test")
    assert match["name"] == "A"

    # Should match B (gamma)
    match = idx.find_best("gamma only")
    assert match["name"] == "B"


def test_simple_keyword_index_returns_none_when_no_match(tmp_path):
    kb_dir = tmp_path / "kb"
    apps = kb_dir / "applications"
    apps.mkdir(parents=True)

    write_yaml(apps / "a.yaml", {"name": "A", "keywords": ["alpha"]})

    idx = SimpleKeywordIndex(str(kb_dir))
    idx.index()
    match = idx.find_best("no overlap here")
    assert match is None


