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

from adw_modules.task_file import Task, adw_branch, task_branch


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def ensure_worktree(repo: Path, state_dir: Path, task: Task, adw_id: str) -> Path:
    worktree = state_dir / "worktree"
    if worktree.exists():
        return worktree

    tbranch = task_branch(task)
    subprocess.run(["git", "branch", tbranch, "origin/main"], cwd=repo, capture_output=True, text=True)
    subprocess.run(["git", "branch", tbranch, "main"], cwd=repo, capture_output=True, text=True)

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


def mr_create(worktree: Path, source: str, target: str, title: str, assignee_self: bool = False) -> str:
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

    # Restart recovery: an MR for this branch may already exist.
    listing = _run(worktree, "glab", "mr", "list", "--source-branch", source, "--output", "json")
    mrs = json.loads(listing.stdout)
    if not mrs:
        raise RuntimeError(f"glab mr create failed and no existing MR found: {result.stderr.strip()}")
    return mrs[0]["web_url"]


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


def mr_merge(worktree: Path, source: str) -> None:
    _run(worktree, "glab", "mr", "merge", source, "--yes")


def remove_worktree(repo: Path, state_dir: Path) -> None:
    _run(repo, "git", "worktree", "remove", "--force", str(state_dir / "worktree"))
