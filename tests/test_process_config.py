import sys, pathlib, textwrap, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adws"))
from adw_modules import process_config as pcmod

GOOD = textwrap.dedent("""\
    default-workflow: full
    slicing: off
    models: {plan: p-strong, implement: p-mid, review: p-strong, aux: p-cheap}
    workflows: [full, lite]
    checks: {test-command: "echo test", ci-gate: on, max-repair-cycles: 3}
""")

def _repo(tmp_path, cfg=GOOD):
    d = tmp_path / "repo" / "docs" / "agents"; d.mkdir(parents=True)
    (d / "process-config.yml").write_text(cfg, encoding="utf-8")
    return tmp_path / "repo"

def test_loads_and_maps_keys(tmp_path):
    pc = pcmod.load_process_config(_repo(tmp_path))
    assert pc.default_workflow == "full" and pc.ci_gate is True
    assert pc.models["implement"] == "p-mid" and pc.max_repair_cycles == 3

def test_replace_me_rejected(tmp_path):
    bad = GOOD.replace('"echo test"', '"REPLACE-ME"')
    with pytest.raises(SystemExit):
        pcmod.load_process_config(_repo(tmp_path, bad))

def test_unknown_workflow_rejected(tmp_path):
    pc = pcmod.load_process_config(_repo(tmp_path))
    with pytest.raises(SystemExit):
        pcmod.validate_workflow(pc, "turbo")

def test_build_sssf_config(tmp_path):
    pc = pcmod.load_process_config(_repo(tmp_path))
    cfg = pcmod.build_sssf_config(pc, tmp_path / "state", tmp_path / "wt")
    agents = {a.name: a for a in cfg.agents}
    assert agents["planner"].model == "p-strong"
    assert agents["builder"].writes is None
    assert "docs/agents/" in cfg.defaults.protected_files
