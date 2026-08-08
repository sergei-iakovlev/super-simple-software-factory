"""Git/glab mechanics for the pipeline: worktree, ADW-trailer commits, MR ops.

Every subprocess call passes `cwd` explicitly — never rely on process cwd
(git_helper._git in this repo has that bug; do not repeat it here).
"""

from __future__ import annotations

import json
import re
import subprocess
import time
import urllib.parse
from pathlib import Path

from adw_modules.task_file import Task, adw_branch, set_status, task_branch


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _base_branch_file(state_dir: Path) -> Path:
    return state_dir / "base_branch.txt"


def base_branch(state_dir: Path) -> str:
    """The branch the task branch was cut from — recorded by `ensure_worktree` at pipeline start."""
    return _base_branch_file(state_dir).read_text(encoding="utf-8").strip()


def ensure_worktree(repo: Path, state_dir: Path, task: Task, adw_id: str) -> Path:
    worktree = state_dir / "worktree"
    if worktree.exists():
        return worktree

    # The task branch cuts from whatever branch is currently checked out in
    # `repo` — not a hardcoded main. This lets the pipeline run against a
    # task filed on an in-progress feature branch without forcing an
    # unrelated merge through main first.
    base = _run(repo, "git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if base == "HEAD":
        raise SystemExit("cannot start the pipeline from a detached HEAD; checkout a branch in the repo first")
    _base_branch_file(state_dir).write_text(base, encoding="utf-8")

    tbranch = task_branch(task)
    # Prefer the remote tip of base (keeps a restart consistent even if the
    # local branch has since moved), fall back to the local ref for a base
    # branch that was never pushed.
    subprocess.run(["git", "branch", tbranch, f"origin/{base}"], cwd=repo, capture_output=True, text=True)
    subprocess.run(["git", "branch", tbranch, base], cwd=repo, capture_output=True, text=True)
    # The adw->task MR (created in `finish`) needs this branch to exist on the
    # remote as its target — without this push, glab creates the MR against a
    # target ref GitLab can't resolve, which it then reports as unmergeable
    # ("has_conflicts") instead of "branch not found".
    subprocess.run(["git", "push", "-u", "origin", tbranch], cwd=repo, capture_output=True, text=True)

    abranch = adw_branch(adw_id, task)
    _run(repo, "git", "worktree", "add", str(worktree), "-B", abranch, tbranch)
    return worktree


def commit_all(worktree: Path, message: str, adw_id: str) -> str:
    _run(worktree, "git", "add", "-A")
    status = _run(worktree, "git", "status", "--porcelain").stdout
    if not status.strip():
        return ""
    full_message = f"{message}\n\nADW: {adw_id}"
    _run(worktree, "git", "commit", "-m", full_message)
    return _run(worktree, "git", "rev-parse", "--short", "HEAD").stdout.strip()


def push(worktree: Path, branch: str) -> None:
    _run(worktree, "git", "push", "-u", "origin", branch)


def _origin_project_path(worktree: Path) -> str:
    url = _run(worktree, "git", "remote", "get-url", "origin").stdout.strip()
    path = re.sub(r"^.*?[:/](?=[^/]+/[^/]+(?:\.git)?$)", "", url)
    path = path.removesuffix(".git")
    return path


def _find_mr(worktree: Path, source: str) -> dict | None:
    """Existing MR for `source`, any state (opened/merged/closed) — dedup + merge-status source of truth."""
    listing = subprocess.run(
        ["glab", "mr", "list", "--source-branch", source, "--all", "--output", "json"],
        cwd=worktree, capture_output=True, text=True,
    )
    if listing.returncode != 0:
        return None
    mrs = json.loads(listing.stdout or "[]")
    return mrs[0] if mrs else None


def mr_create(worktree: Path, source: str, target: str, title: str, assignee_self: bool = False) -> str:
    # Check first, not create-then-recover-on-error: a retry after a crash
    # mid-`finish` must never spawn a second MR for the same branch (this is
    # what produced duplicate MRs on the video-transcribe smoke run).
    existing = _find_mr(worktree, source)
    if existing is not None:
        return existing["web_url"]

    args = [
        "glab", "mr", "create",
        "--source-branch", source, "--target-branch", target,
        "--title", title, "--description", "", "--yes",
    ]
    if assignee_self:
        args += ["--assignee", "@me"]
    result = subprocess.run(args, cwd=worktree, capture_output=True, text=True)
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("http"):
                return line
        return result.stdout.strip()

    # Lost a race (MR appeared between the check above and this call).
    existing = _find_mr(worktree, source)
    if existing is not None:
        return existing["web_url"]
    raise RuntimeError(f"glab mr create failed and no existing MR found: {result.stderr.strip()}")


def wait_ci_green(worktree: Path, branch: str, timeout_s: int = 3600) -> None:
    project_path = urllib.parse.quote(_origin_project_path(worktree), safe="")
    deadline = time.monotonic() + timeout_s
    while True:
        result = subprocess.run(
            ["glab", "api", f"projects/{project_path}/pipelines?ref={branch}&per_page=1"],
            cwd=worktree, capture_output=True, text=True,
        )
        if result.returncode == 0:
            pipelines = json.loads(result.stdout)
            if pipelines:
                pipeline = pipelines[0]
                status = pipeline.get("status")
                if status == "success":
                    return
                if status in ("failed", "canceled"):
                    raise SystemExit(f"CI failed for {branch}: {pipeline.get('web_url')}")

        if time.monotonic() >= deadline:
            raise SystemExit(f"CI timed out after {timeout_s}s for {branch}")
        time.sleep(30)


def mr_merge(worktree: Path, source: str, attempts: int = 5, delay_s: float = 5.0) -> None:
    """Idempotent, retrying merge.

    Right after `mr_create`, GitLab's merge_status is often still "checking"
    (pipeline evaluating mergeability) and an immediate `glab mr merge` fails
    with exit 1 even though the MR is fine — this is what turned the
    video-transcribe smoke run's single MR into three. Poll `_find_mr` for
    "merged" first (covers retries after a crash post-merge), then retry the
    merge call itself with a short backoff.
    """
    existing = _find_mr(worktree, source)
    if existing is not None and existing.get("state") == "merged":
        return

    last_err = ""
    for attempt in range(attempts):
        result = subprocess.run(["glab", "mr", "merge", source, "--yes"], cwd=worktree, capture_output=True, text=True)
        if result.returncode == 0:
            return
        last_err = result.stderr.strip()
        existing = _find_mr(worktree, source)
        if existing is not None and existing.get("state") == "merged":
            return  # merged despite the nonzero exit (e.g. race with a prior attempt)
        if attempt < attempts - 1:
            time.sleep(delay_s)
    raise RuntimeError(f"glab mr merge failed after {attempts} attempts: {last_err}")


def remove_worktree(repo: Path, state_dir: Path) -> None:
    _run(repo, "git", "worktree", "remove", "--force", str(state_dir / "worktree"))


def flip_status_on_task_branch(state_dir: Path, task: Task, status: str, adw_id: str) -> None:
    """Flip the task file's status, committed as the FIRST commit on the adw branch.

    There is nowhere else to make this edit: the task branch is not checked out
    anywhere (the worktree holds the adw branch), so the flip is made there and
    rides to the task branch at the adw->task merge in `finish_on_task_branch`.
    Trade-off recorded in FORK.md: `in-progress` becomes visible on the task
    branch only once the adw branch is pushed, not the instant the ADW starts.
    """
    worktree = state_dir / "worktree"
    set_status(worktree / task.rel_path, status)
    commit_all(worktree, f"chore: {status} status for {task.slug}", adw_id)


def finish_on_task_branch(state_dir: Path, task: Task, adw_id: str) -> str:
    """After the adw->task MR is merged: land on the task branch, mark it done, open task->base.

    "base" is whatever branch `ensure_worktree` cut the task branch from —
    not hardcoded main — so the final MR returns to the same branch the work
    started on. Returns the task->base MR url (or the existing one, recovered
    the same way `mr_create` recovers from a restart).
    """
    worktree = state_dir / "worktree"
    tbranch = task_branch(task)
    base = base_branch(state_dir)
    _run(worktree, "git", "fetch", "origin")
    _run(worktree, "git", "checkout", tbranch)
    _run(worktree, "git", "pull")
    set_status(worktree / task.rel_path, "done")
    commit_all(worktree, f"chore: done status for {task.slug}", adw_id)
    push(worktree, tbranch)
    return mr_create(worktree, tbranch, base, f"task: {task.slug}", assignee_self=True)
