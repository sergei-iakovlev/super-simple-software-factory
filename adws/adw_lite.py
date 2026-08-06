#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pydantic", "python-dotenv", "pyyaml", "rich"]
# ///
"""ADW lite — plan -> build -> test repair loop -> readable -> finish. No agent review.

Usage:
    uv run adws/adw_lite.py --repo <path> --task <docs/queue/.../file.md> [--adw-id a1b2c3d4]

Phases: request(engineer) -> launch(code) -> plan(agent) -> build(agent) ->
[test(code) -> fix(agent)] x N -> readable(agent) -> finish(code).

Task-file driven, unlike upstream's per-script prompt argument: the task under
docs/queue/ names its own workflow, PRD, plan, and review paths, so this ADW
only needs a repo and a task file to know exactly what to do. `adw_full.py`
(B8) copies this file and inserts an agent review loop between build and the
test loop — keep this one flat and readable, it is the reference shape.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adw_modules import agents, gates, pipeline_git as pg, process_config as pcmod
from adw_modules import quality, session, task_file as tf
from adw_modules.data_types import AgentCall, BuildOutput, GenericOutput, PhaseParams, PlanOutput
from adw_modules.utils import new_id

WORKFLOW = "lite"


def main(repo: str, task_rel: str, adw_id: str | None) -> int:
    repo_path = Path(repo).resolve()
    fork = pcmod.load_fork_config()
    pc = pcmod.load_process_config(repo_path)
    pcmod.validate_workflow_scripts(pc)
    task = tf.load_task(repo_path, task_rel)
    workflow = task.workflow or pc.default_workflow
    if workflow != WORKFLOW:
        sys.exit(f"task wants workflow '{workflow}', this is adw_{WORKFLOW}.py")
    tf.check_not_blocked(repo_path, task)
    if not (repo_path / tf.sibling(task, "prd")).exists():
        sys.exit(f"not pipeline-ready: missing PRD {tf.sibling(task, 'prd')}")

    # Minted here (not left to session.ensure) because the worktree, branch
    # names, and state_dir all need the SAME id before a Run exists to hand one
    # back — session.ensure(cfg, adw_id) then just uses the id we pass it.
    adw_id = adw_id or new_id(8)
    state_dir = fork.state_root / repo_path.name / adw_id
    state_dir.mkdir(parents=True, exist_ok=True)
    worktree = pg.ensure_worktree(repo_path, state_dir, task, adw_id)
    os.chdir(worktree)  # SSSF internals are cwd-relative; state paths are absolute

    cfg = pcmod.build_sssf_config(pc, state_dir, worktree)
    agents.validate(cfg, ["planner", "builder", "readable"])
    quality.TEST_COMMAND = pc.test_command
    run = session.ensure(cfg, adw_id)
    run.extra_vars = {
        "skills_root": str(fork.skills_root),
        "task_context": (
            f"Task file: {task.rel_path}\nPRD: {tf.sibling(task, 'prd')}\n"
            f"Plan path: {tf.sibling(task, 'plan')}\nReview path: {tf.sibling(task, 'review')}\n"
            f"Definition of done:\n{task.definition_of_done}"
        ),
    }
    task_branch, adw_branch = tf.task_branch(task), tf.adw_branch(adw_id, task)

    with run.phase(PhaseParams(name="request", kind="engineer", owner=run.engineer,
                               description="Capture task and launch parameters")) as ph:
        ph.log(input=f"{task.rel_path} @ {repo_path} [{workflow}]")

    with run.phase(PhaseParams(name="launch", kind="code", owner="pipeline",
                               description="Flip task to in-progress on the task branch")) as ph:
        if task.status == "queued":
            pg.flip_status_on_task_branch(state_dir, task, "in-progress", adw_id)
        ph.log(status="in-progress")

    with run.phase(PhaseParams(name="plan", kind="agent", owner="planner",
                               description="Write the implementation plan via writing-plans")) as ph:
        plan_env = ph.call(AgentCall(output_type=PlanOutput,
                                     prompt=f"Plan the task. Save to {tf.sibling(task, 'plan')}.",
                                     gates=[gates.artifacts_exist, gates.files_non_empty]))
    pg.commit_all(worktree, plan_env.commit_message or f"docs: plan for {task.slug}", adw_id)

    with run.phase(PhaseParams(name="build", kind="agent", owner="builder", retries=1,
                               description="Implement the plan test-first")) as ph:
        build_env = ph.call(AgentCall(output_type=BuildOutput, previous=plan_env,
                                      prompt=f"Implement the plan at {tf.sibling(task, 'plan')}.",
                                      gates=[gates.diff_matches_claims]))
    pg.commit_all(worktree, build_env.commit_message or f"feat: {task.slug}", adw_id)

    prev, test = build_env, None
    for i in range(1, pc.max_repair_cycles + 1):
        with run.phase(PhaseParams(name=f"test_{i}", kind="code", owner="pipeline",
                                   description="Run the repo test command")) as ph:
            test = quality.run_tests(run)
            ph.log(command=pc.test_command, passed=test.passed)
        if test.passed:
            break
        if i == pc.max_repair_cycles:
            sys.exit(f"[adw {adw_id}] phase test_{i} failed after {pc.max_repair_cycles} repair cycles; "
                     f"restart: uv run adws/adw_lite.py --repo {repo} --task {task_rel} --adw-id {adw_id}")
        with run.phase(PhaseParams(name=f"fix_{i}", kind="agent", owner="builder",
                                   description="Fix failing tests")) as ph:
            prev = ph.call(AgentCall(output_type=BuildOutput, previous=quality.as_envelope(test, "test"),
                                     prompt="Tests failed. Fix the root cause; do not weaken tests."))
        pg.commit_all(worktree, f"fix: repair cycle {i} for {task.slug}", adw_id)

    with run.phase(PhaseParams(name="readable", kind="agent", owner="readable",
                               description="Generate Russian readers for PRD/ADR")) as ph:
        ph.call(AgentCall(output_type=GenericOutput, previous=prev,
                          prompt="Generate/refresh readers for this task's PRD and any ADRs it references."))
    pg.commit_all(worktree, f"docs: readable readers for {task.slug}", adw_id)

    with run.phase(PhaseParams(name="finish", kind="code", owner="pipeline",
                               description="Merge adw->task, mark done, open MR to main")) as ph:
        pg.push(worktree, adw_branch)
        mr = pg.mr_create(worktree, adw_branch, task_branch, f"adw: {task.slug} [{adw_id}]")
        if pc.ci_gate:
            pg.wait_ci_green(worktree, adw_branch)
        pg.mr_merge(worktree, adw_branch)
        task_mr = pg.finish_on_task_branch(state_dir, task, adw_id)
        ph.log(mr=mr, task_mr=task_mr)

    rc = run.finish(accepted=test is not None and test.passed,
                    reason=f"the suite still failed after {pc.max_repair_cycles} repair cycle(s)")
    if rc == 0:
        pg.remove_worktree(repo_path, state_dir)
    return rc


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--adw-id", default=None)
    a = p.parse_args()
    sys.exit(main(a.repo, a.task, a.adw_id))
