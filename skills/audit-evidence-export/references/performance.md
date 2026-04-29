# Performance patterns — audit-evidence-export

This skill pulls events and comments per task across the full close period — easily 200+ tasks for a multi-entity close. Apply these patterns in order.

## Fan out the per-task event pull

After listing tasks for the period, dispatch one subagent per batch of ~50 tasks in a single Agent tool message. Each subagent calls `get_task_events` and `get_task_comments` for its batch, runs the bundled parsers, and returns a normalized JSON. Merge in the parent before writing the workbook.

In environments without subagents, run batches sequentially but still cache per task.

## Use the bundled parsers

`scripts/parse_events.py`, `parse_tasks.py`, and `parse_context.py` shape raw MCP responses into the audit workbook structure. Use them. Extend them if new aggregation is needed (review-cycle counts, sign-off latencies). Avoid in-context event timeline reasoning.

## Materiality is auditor-driven

Auditors typically want every task. Do not silently skip immaterial ones. Ask the user upfront via `AskUserQuestion` whether the export should be (a) every task in the period, (b) reconciliations only, (c) tasks with sign-off events only, or (d) tasks above a materiality threshold the auditor specified. Default to (a).

## Window is bound by the close period

No widening logic needed. If the user passes a quarter or fiscal year, confirm whether to produce one combined workbook or one per period before fanning out.

## Checkpoint per task

Each subagent writes to `outputs/.audit_evidence_cache/{period_id}/{task_id}.json` before returning. A re-run skips tasks whose checkpoint exists. This matters for late-activity re-pulls — only the changed tasks re-fetch.

## Validate scope before fan-out

Before dispatching subagents, confirm:
- The `period_id` exists in `get_workspace_context`.
- `list_tasks` returned >0 tasks for the period.
- The selected scope mode (all tasks / recs only / sign-off only / above-threshold) is confirmed with the user.

A wrong period or unconfirmed scope produces a useless audit workbook.

## Short-circuit on empty

If `list_tasks` returns 0 tasks for the period, tell the user the period has no activity and stop. Do not produce an empty workbook.

## Stream progress during fan-out

Emit a one-line update every ~50 tasks (`"Pulled events for 100 of 350 tasks..."`).

## Subagent prompt shape

Each subagent receives, as inputs only:
- The list of `task_keys` in its batch, the user-ID-to-name map, the cache directory.

Each subagent returns:
- `{batch_index, parsed_path: <json file>, task_count, event_count}`.

Subagents have no conversation history. Pass everything they need as inputs. Do not assume access to the workspace context or the full task list.
