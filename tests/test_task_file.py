import sys, pathlib, textwrap, pytest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adws"))
from adw_modules import task_file as tf

TASK = textwrap.dedent("""\
    ---
    status: queued
    workflow: lite
    blocked-by: []
    ---
    # Smoke task

    ## What to do
    Say hello.

    ## Definition of done
    hello.txt exists and contains "hello".
""")

def _mk(tmp_path, rel="docs/queue/2026-08/06-1200-smoke.md", text=TASK):
    p = tmp_path / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8"); return p

def test_parse(tmp_path):
    _mk(tmp_path)
    t = tf.load_task(tmp_path, "docs/queue/2026-08/06-1200-smoke.md")
    assert (t.slug, t.shard, t.stem) == ("smoke", "2026-08", "06-1200-smoke")
    assert t.workflow == "lite" and "hello.txt" in t.definition_of_done

def test_branches_and_siblings(tmp_path):
    _mk(tmp_path)
    t = tf.load_task(tmp_path, "docs/queue/2026-08/06-1200-smoke.md")
    assert tf.task_branch(t) == "task/2026-08/06-1200-smoke"
    assert tf.adw_branch("ab12cd34", t) == "adw/ab12cd34-smoke"
    assert tf.sibling(t, "plan") == "docs/queue/2026-08/06-1200-smoke-plan.md"

def test_missing_dod_rejected(tmp_path):
    _mk(tmp_path, text=TASK.replace("## Definition of done", "## Notes"))
    with pytest.raises(SystemExit):
        tf.load_task(tmp_path, "docs/queue/2026-08/06-1200-smoke.md")

def test_set_status_preserves_rest(tmp_path):
    p = _mk(tmp_path)
    tf.set_status(p, "in-progress")
    text = p.read_text(encoding="utf-8")
    assert "status: in-progress" in text and "workflow: lite" in text

def test_blocked(tmp_path):
    blocker_rel = "docs/queue/2026-08/06-1100-first.md"
    _mk(tmp_path, blocker_rel, TASK.replace("workflow: lite", "workflow: full"))
    blocked = TASK.replace("blocked-by: []", f"blocked-by: [{blocker_rel}]")
    _mk(tmp_path, "docs/queue/2026-08/06-1200-smoke.md", blocked)
    t = tf.load_task(tmp_path, "docs/queue/2026-08/06-1200-smoke.md")
    with pytest.raises(SystemExit):
        tf.check_not_blocked(tmp_path, t)
