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


class _FakeResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def test_mr_create_dedups_against_existing_mr(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, cwd=None, capture_output=None, text=None):
        calls.append(args)
        if args[:3] == ["glab", "mr", "list"]:
            return _FakeResult(0, '[{"web_url": "https://gitlab/mr/1", "state": "opened"}]')
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    url = pg.mr_create(tmp_path, "adw/x", "task/x", "title")
    assert url == "https://gitlab/mr/1"
    assert not any(a[:3] == ["glab", "mr", "create"] for a in calls)  # never re-created


def test_mr_merge_noop_when_already_merged(tmp_path, monkeypatch):
    calls = []

    def fake_run(args, cwd=None, capture_output=None, text=None):
        calls.append(args)
        return _FakeResult(0, '[{"web_url": "https://gitlab/mr/1", "state": "merged"}]')

    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    pg.mr_merge(tmp_path, "adw/x")
    assert not any(a[:3] == ["glab", "mr", "merge"] for a in calls)  # never called merge


def test_mr_merge_retries_then_succeeds(tmp_path, monkeypatch):
    state = {"merge_calls": 0}

    def fake_run(args, cwd=None, capture_output=None, text=None):
        if args[:3] == ["glab", "mr", "list"]:
            return _FakeResult(0, "[]")  # not found yet -> not merged
        if args[:3] == ["glab", "mr", "merge"]:
            state["merge_calls"] += 1
            if state["merge_calls"] < 3:
                return _FakeResult(1, "", "not mergeable yet")
            return _FakeResult(0, "merged!")
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    monkeypatch.setattr(pg.time, "sleep", lambda s: None)
    pg.mr_merge(tmp_path, "adw/x", attempts=5, delay_s=0)
    assert state["merge_calls"] == 3


def test_mr_merge_raises_after_exhausting_attempts(tmp_path, monkeypatch):
    def fake_run(args, cwd=None, capture_output=None, text=None):
        if args[:3] == ["glab", "mr", "list"]:
            return _FakeResult(0, "[]")
        if args[:3] == ["glab", "mr", "merge"]:
            return _FakeResult(1, "", "still checking")
        raise AssertionError(f"unexpected call: {args}")

    monkeypatch.setattr(pg.subprocess, "run", fake_run)
    monkeypatch.setattr(pg.time, "sleep", lambda s: None)
    try:
        pg.mr_merge(tmp_path, "adw/x", attempts=2, delay_s=0)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "still checking" in str(e)
