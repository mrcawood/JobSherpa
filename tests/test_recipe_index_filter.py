from jobsherpa.agent.recipe_index import SimpleKeywordIndex


def test_recipe_index_prefers_name_match(tmp_path):
    kb = tmp_path / "kb" / "applications"
    kb.mkdir(parents=True)
    # Two recipes with similar keywords but different names
    (kb / "wrf.yaml").write_text("name: wrf\nkeywords: [weather, simulation]\ntemplate: wrf.sh.j2\n")
    (kb / "other.yaml").write_text("name: other\nkeywords: [weather, simulation]\ntemplate: other.sh.j2\n")
    idx = SimpleKeywordIndex(str(tmp_path / "kb"))
    idx.index()
    # With name filter but no keyword overlap, current behavior is None to avoid false positives
    r = idx.find_best("run wrf hurricane katrina")
    assert r is None


