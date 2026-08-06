import sys, pathlib, subprocess
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "adws"))
from adw_modules import pipeline_git as pg, task_file as tf

def _git(cwd, *args): subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

def _repo(tmp_path):
    r = tmp_path / "repo"; r.mkdir(); _git(r, "init", "-b", "main")
    _git(r, "config", "user.email", "t@t"); _git(r, "config", "user.name", "t")
    (r / "a.txt").write_text("a"); _git(r, "add", "-A"); _git(r, "commit", "-m", "init")
    return r

def test_worktree_lifecycle(tmp_path):
    r = _repo(tmp_path); state = tmp_path / "state"; state.mkdir()
    task = tf.Task(path=r/"docs/queue/2026-08/06-1200-smoke.md", rel_path="docs/queue/2026-08/06-1200-smoke.md",
                   slug="smoke", shard="2026-08", stem="06-1200-smoke", status="queued",
                   workflow=None, blocked_by=[], title="t", body="", definition_of_done="d")
    wt = pg.ensure_worktree(r, state, task, "ab12cd34")
    assert wt.exists()
    out = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=wt, check=True, capture_output=True, text=True)
    assert out.stdout.strip() == "adw/ab12cd34-smoke"
    assert pg.ensure_worktree(r, state, task, "ab12cd34") == wt  # idempotent restart

def test_commit_trailer(tmp_path):
    r = _repo(tmp_path)
    (r / "b.txt").write_text("b")
    sha = pg.commit_all(r, "feat: b", "ab12cd34")
    assert sha
    msg = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=r, check=True, capture_output=True, text=True).stdout
    assert "ADW: ab12cd34" in msg
    assert pg.commit_all(r, "noop", "ab12cd34") == ""  # clean tree
