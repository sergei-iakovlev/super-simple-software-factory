## Variables

### task_context
{{task_context}}

### prompt
{{prompt}}

### previous_envelope
{{previous_envelope}}

## Task

Write the implementation plan for this queue task at the plan path named in task_context.

## Report

Respond with ONLY a JSON object:
{"status": "success", "summary": "one line", "artifacts": ["<plan path>"], "notes_for_next_agent": "key risks or decisions the builder must know", "commit_message": "docs: implementation plan for <slug>"}
