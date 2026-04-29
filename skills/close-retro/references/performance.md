# Performance patterns — close-retro

Event batches are the bottleneck — each takes a few seconds and the responses are 70–190K. Apply these patterns in order.

## Always parse MCP results with the bundled scripts

Raw MCP responses are 50–300K characters. Use `scripts/parse_tasks.py`, `parse_events.py`, and `parse_context.py`. Avoid in-context processing.

## Extract the user map early

Event data contains user IDs, not names. Parse the workspace context first so the ID→name mapping exists before processing events.

## Fan out event batches in parallel

Dispatch event batches as parallel subagents in a single Agent tool message. Each subagent owns one batch of ~15 task keys, calls `get_task_events`, runs `parse_events.py` on its slice, and returns a small JSON summary. Merge in the parent. This collapses a sequential 6–10 batch run into roughly the time of a single batch.

In environments without subagents, run batches sequentially but still cache per batch.

## Batch sizing — by task_keys, ~15 per batch

The events API returns 500 on unfiltered calls. Fifteen task keys per batch keeps response sizes manageable (70–190K). For workspaces with many tasks, 6–10 batches of 15 keys each (90–150 tasks) gives reliable medians and distributions. Scale up for smaller workspaces where full coverage is quick.

## Apply a materiality gate before fanning out events

When a period has >100 tasks, prioritize: pull events first for late tasks, tasks with multiple review cycles, and reconciliations over a user-defined materiality threshold. Pull events for the remainder only if requested. Default cutoff: top 100 tasks by these signals; allow user override.

## Confirm period scope before pulling

If the user says "this close" while a period is mid-flight, ask via `AskUserQuestion` whether to include in-flight or wait for close completion. If they pass a quarter or half, confirm one combined retro vs. one per month before fanning out.

## Checkpoint per batch

Each subagent writes parsed events to `outputs/.close_retro_cache/{period_id}/batch_{n}.json` before returning. Re-runs (e.g., user wants a different digest framing on the same data) read from cache rather than re-fetching.

## Skip the HTML dashboard by default

The Slack digest is what people actually use. The dashboard is nice for presentations but is not worth the extra build time unless requested.

## Validate scope before fan-out

Before fanning out event batches, confirm:
- The `period_id` exists in `get_workspace_context`.
- `list_tasks` returned >0 tasks for the period.
- The user-ID-to-name map is populated.

A wrong period or unparsed user map produces a digest with cryptic IDs instead of names.

## Short-circuit on empty

If 0 tasks for the period, report "No tasks found" and stop. If 0 events come back across all batches, skip efficiency metrics and report status-based metrics only — do not fabricate event-derived numbers.

## Stream progress during fan-out

Emit a one-line update every batch (`"Pulled events for batch 4 of 8..."`).

## Subagent prompt shape

Each subagent receives, as inputs only:
- The list of `task_keys` in its batch, the cache directory, the path to `parse_events.py`.

Each subagent returns:
- `{batch_index, parsed_path: <json file>, event_count, late_count, review_cycles}`.

Subagents have no conversation history.
