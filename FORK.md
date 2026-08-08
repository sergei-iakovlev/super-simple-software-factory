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
- **Task branch cuts from the current branch, not main**: `ensure_worktree` bases the task branch on whatever branch is checked out in the target repo when the pipeline starts (recorded in `state/.../base_branch.txt`), and the final task→base MR targets that same branch. A task filed while working on a feature branch doesn't force an unrelated merge through main first. Detached HEAD is rejected with a clear error rather than silently branching from a commit with no branch to MR back into.
- **pi stderr in trace**: `pi` (the coding agent invocation) stderr is captured into the SQLite trace db alongside stdout, so failures are visible in the trace instead of only on the console.
- **`in-progress` visibility, simplified**: `adw_lite`'s `launch` phase flips the task file's status on the adw branch (the only branch the worktree has checked out), not on the task branch directly — the task branch is never checked out anywhere at launch time. The flip rides to the task branch at the adw->task merge in `finish`, so `in-progress` becomes visible in the repo once the adw branch is pushed (minutes after launch starts), not the instant the ADW begins. Accepted as a deliberate simplification; revisit if a reader needs to see `in-progress` before the first commit lands.

## Update procedure

When pulling in upstream changes:

1. Diff the upstream `templates/adws/` and `templates/prompt_engineering/` against this repo's `adws/` and `prompts/`.
2. Port changes consciously, file by file — do not bulk-copy over the top, since the divergences above are intentional and would be silently reverted by a blind overwrite.
3. Re-run the sanity import check (see Step 6 in the B1 task) and the fork test suite after porting.
