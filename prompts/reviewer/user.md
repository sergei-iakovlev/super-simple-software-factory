## Variables

### task_context
{{task_context}}

### prompt
{{prompt}}

### previous_envelope
{{previous_envelope}}

## Task

Review and write the report.

## Report

Respond with ONLY a JSON object:
{"status": "success", "summary": "one line", "artifacts": ["<review path>"], "notes_for_next_agent": "key risks or decisions the builder must know", "approved": true, "findings": [{"requirement": "...", "met": true, "evidence": "..."}], "blocking": []}
