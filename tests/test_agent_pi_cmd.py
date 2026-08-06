import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adws"))

def test_pi_path_is_split_into_argv(monkeypatch):
    monkeypatch.setenv("PI_PATH", "node C:/tools/pi/cli.js")
    import importlib
    from adw_modules import agent_pi
    importlib.reload(agent_pi)
    assert agent_pi.PI_CMD == ["node", "C:/tools/pi/cli.js"]

def test_default_pi_cmd(monkeypatch):
    monkeypatch.delenv("PI_PATH", raising=False)
    import importlib
    from adw_modules import agent_pi
    importlib.reload(agent_pi)
    assert agent_pi.PI_CMD == ["pi"]
