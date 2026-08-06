## Variables

### task_context
{{task_context}}

### prompt
{{prompt}}

### previous_envelope
{{previous_envelope}}

## Task

Implement the plan. If previous_envelope contains test failures, fix them.

## Report

Respond with ONLY a JSON object:
{"status": "success", "summary": "one line", "artifacts": [], "notes_for_next_agent": "key risks or decisions the reviewer must know", "changed_files": ["src/x.py"], "commit_message": "feat: <slug>"}
