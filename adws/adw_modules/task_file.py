"""Parse task files under docs/queue/: frontmatter, Definition of done, branches, status."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_STEM_PREFIX_RE = re.compile(r"^\d{2}-\d{4}-")
_DOD_RE = re.compile(r"^##\s+definition of done\s*$(.*?)(?=^##\s|\Z)", re.IGNORECASE | re.DOTALL | re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)


class Task(BaseModel):
    path: Path
    rel_path: str
    slug: str
    shard: str
    stem: str
    status: str
    workflow: Optional[str] = None
    blocked_by: list[str] = []
    title: str
    body: str
    definition_of_done: str


def load_task(repo: Path, task_rel: str) -> Task:
    path = repo / task_rel
    if not path.exists():
        raise SystemExit(f"task file not found: {path}")
    rel_path = Path(task_rel).as_posix()
    if not rel_path.startswith("docs/queue/"):
        raise SystemExit(f"task file must be under docs/queue/: {rel_path}")

    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    frontmatter = yaml.safe_load(m.group(1)) if m else {}
    body = text[m.end():] if m else text

    dod_match = _DOD_RE.search(body)
    if not dod_match:
        raise SystemExit(f"{rel_path}: no 'Definition of done' section")
    definition_of_done = dod_match.group(1).strip()

    title_match = _TITLE_RE.search(body)
    title = title_match.group(1).strip() if title_match else ""

    stem = path.stem
    shard = path.parent.name
    slug = _STEM_PREFIX_RE.sub("", stem)

    return Task(
        path=path,
        rel_path=rel_path,
        slug=slug,
        shard=shard,
        stem=stem,
        status=frontmatter.get("status", ""),
        workflow=frontmatter.get("workflow"),
        blocked_by=frontmatter.get("blocked-by") or [],
        title=title,
        body=body,
        definition_of_done=definition_of_done,
    )


def task_branch(task: Task) -> str:
    return f"task/{task.shard}/{task.stem}"


def adw_branch(adw_id: str, task: Task) -> str:
    return f"adw/{adw_id}-{task.slug}"


def sibling(task: Task, suffix: str) -> str:
    # PRDs get their own top-level folder (like ADRs) instead of living
    # alongside the queue task; plan/review/research stay queue siblings.
    base = "docs/prd" if suffix == "prd" else "docs/queue"
    return f"{base}/{task.shard}/{task.stem}-{suffix}.md"


def set_status(path: Path, status: str) -> None:
    text = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SystemExit(f"{path}: no frontmatter block")
    frontmatter = re.sub(r"^status:.*$", f"status: {status}", m.group(1), count=1, flags=re.MULTILINE)
    new_text = text[: m.start(1)] + frontmatter + text[m.end(1):]
    path.write_text(new_text, encoding="utf-8")


def check_not_blocked(repo: Path, task: Task) -> None:
    for blocker_rel in task.blocked_by:
        blocker = load_task(repo, blocker_rel)
        if blocker.status != "done":
            raise SystemExit(
                f"{task.rel_path}: blocked by {blocker_rel} (status: {blocker.status})"
            )
