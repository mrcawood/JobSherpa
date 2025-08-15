from jobsherpa.kb.app_registry import AppRegistry


def test_app_registry_roundtrip(tmp_path):
    reg_path = tmp_path / ".jobsherpa" / "apps.json"
    reg = AppRegistry(str(reg_path))
    assert reg.get_exe_path("Frontera", "wrf") is None
    reg.set_exe_path("Frontera", "wrf", "/opt/wrf.exe")
    assert reg.get_exe_path("Frontera", "wrf") == "/opt/wrf.exe"


