"""Bridge between docs/agents/process-config.yml and SSSF's SSSFConfig."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from adw_modules.data_types import (
    AgentConfig,
    ConfigDefaults,
    ObservabilityConfig,
    PromptEngineering,
    SSSFConfig,
)

FORK_ROOT = Path(__file__).resolve().parents[2]


class ProcessConfig(BaseModel):
    default_workflow: str = Field(alias="default-workflow")
    slicing: bool
    models: dict[str, str]
    workflows: list[str]
    test_command: str
    ci_gate: bool
    max_repair_cycles: int

    model_config = {"populate_by_name": True}


class ForkConfig(BaseModel):
    skills_root: Path
    state_root: Path


def load_process_config(repo: Path) -> ProcessConfig:
    path = repo / "docs" / "agents" / "process-config.yml"
    if not path.exists():
        raise SystemExit(f"process-config.yml not found at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    checks = raw.get("checks", {})
    test_command = checks.get("test-command", "")
    if test_command == "REPLACE-ME":
        raise SystemExit(
            f"{path}: checks.test-command is still 'REPLACE-ME' — set it before running"
        )
    return ProcessConfig(
        **{
            "default-workflow": raw["default-workflow"],
            "slicing": raw["slicing"],
            "models": raw["models"],
            "workflows": raw["workflows"],
            "test_command": test_command,
            "ci_gate": checks.get("ci-gate", False),
            "max_repair_cycles": checks.get("max-repair-cycles", 0),
        }
    )


def load_fork_config() -> ForkConfig:
    path = FORK_ROOT / "fork.config.yml"
    if not path.exists():
        raise SystemExit(f"fork.config.yml not found at {path} — copy fork.config.sample.yml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ForkConfig(skills_root=Path(raw["skills_root"]), state_root=Path(raw["state_root"]))


def _agent(name: str, model: str, writes: list[str] | None) -> AgentConfig:
    prompts_dir = FORK_ROOT / "prompts" / name
    kwargs = dict(
        name=name,
        model=model,
        prompt_engineering=PromptEngineering(
            system=str(prompts_dir / "system.md"),
            user=str(prompts_dir / "user.md"),
        ),
    )
    if writes is not None:
        kwargs["writes"] = writes
    return AgentConfig(**kwargs)


def build_sssf_config(pc: ProcessConfig, state_dir: Path, worktree: Path) -> SSSFConfig:
    agents = [
        _agent("planner", pc.models["plan"], ["docs/queue/"]),
        _agent("builder", pc.models["implement"], None),
        _agent("reviewer", pc.models["review"], ["docs/queue/"]),
        _agent("readable", pc.models["aux"], ["docs/queue/", "docs/adr/"]),
    ]
    defaults = ConfigDefaults(
        protected_files=[
            "docs/agents/",
            ".claude/",
            "docs/adr/",
            "docs/README.md",
            "docs/ideas/README.md",
            "docs/roadmap/README.md",
            "docs/queue/README.md",
            "docs/wayfinders/README.md",
            "docs/queue/**/*-prd.md",
        ],
        data_dir=str(state_dir),
    )
    observability = ObservabilityConfig(db=str(state_dir / "sssf.db"))
    return SSSFConfig(defaults=defaults, observability=observability, agents=agents)


def validate_workflow(pc: ProcessConfig, name: str) -> None:
    if name not in pc.workflows:
        raise SystemExit(f"unknown workflow '{name}'; configured: {pc.workflows}")


def validate_workflow_scripts(pc: ProcessConfig) -> None:
    for name in pc.workflows:
        script = Path(__file__).resolve().parents[1] / f"adw_{name}.py"
        if not script.exists():
            raise SystemExit(f"workflow '{name}' configured but {script} does not exist")
