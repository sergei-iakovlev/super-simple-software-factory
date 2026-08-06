# FORK.md

## Upstream

- URL: https://github.com/sergei-iakovlev/super-simple-software-factory.git
- Pinned commit: `de31374`
- Stock code preserved under `.claude/skills/sssf/`; `adws/` and `prompts/` at the repo root are promoted, live copies of `.claude/skills/sssf/templates/adws/` and `.claude/skills/sssf/templates/prompt_engineering/` respectively, and are the ones actually executed and modified going forward.

## Divergences

- **Central install**: this checkout is not stamped into each target repo. It runs centrally from here, driven against a target repo path, instead of being copied per-project.
- **Windows patches**: adjustments to path handling, shell invocation, and process spawning so the ADWs run under Windows/PowerShell, not just POSIX.
- **process-config.yml bridge**: a bridge layer reads the target repo's `process-config.yml` (single-file, named-workflow convention) and maps it onto SSSF's ADW invocation, rather than each target repo carrying SSSF-specific config.
- **Task-file driven ADWs**: `adw_full` and `adw_lite` are new entry points that take a task file as their unit of work, instead of the upstream per-script argument conventions.
- **Worktree/glab git mechanics**: git worktree creation and GitHub CLI (`glab`)/PR mechanics are adapted for this fork's workflow.
- **pi stderr in trace**: `pi` (the coding agent invocation) stderr is captured into the SQLite trace db alongside stdout, so failures are visible in the trace instead of only on the console.

## Update procedure

When pulling in upstream changes:

1. Diff the upstream `templates/adws/` and `templates/prompt_engineering/` against this repo's `adws/` and `prompts/`.
2. Port changes consciously, file by file — do not bulk-copy over the top, since the divergences above are intentional and would be silently reverted by a blind overwrite.
3. Re-run the sanity import check (see Step 6 in the B1 task) and the fork test suite after porting.
