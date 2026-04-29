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
---

## v1.0 — additional patterns

### Confirm scope upfront when expensive work is implied

Before any heavy data pull, estimate the scope and confirm with the user via `AskUserQuestion` when any of these signals are present:

- Multi-entity request without an explicit entity list (default would be all entities → ask which one).
- Window wider than the skill's default (trailing 12 vs. single-month → ask).
- Large-tier workspace (>5 entities, or >300 tasks expected for the period).
- Account count expected to exceed the materiality gate's typical N (>100 leaves).

When any signal triggers, present concrete options and the projected cost:

> "This will pull 12 months of transactions across 5 entities (~60 API calls, est. 4–8 min). Continue, or narrow scope?"
>
> Entity: <list> — pick one, or 'all' (default)
> Accounts: 'all that exceed materiality' (default), or pick specific accounts
> Materiality: small workspace $1K (default), medium $5K, large $10K, custom

Only proceed after the user confirms. This pattern catches expensive runs before the data is pulled — earlier than fail-fast (after pull) or materiality gate (after pull + parse).

### Session-level cache for cold-start calls

`get_workspace_context`, `list_reports`, and `list_financial_accounts` change rarely within a session and are expensive (60K+ chars each). Write the response to `outputs/.numeric_session_cache/{workspace_id}_{call}.json` after the first call and read from cache on subsequent calls in the same session. TTL ~24h. This benefits any user who runs more than one skill in a session.
### Subagent rule — do not read tool-result content

Subagents must NOT read or display the TSV/JSON content of any tool-result file they handle. Only `cp` the redirected file to the cache path, then `wc -l` (or equivalent) for the line count. After that, return the contracted JSON immediately. Reading the content into context costs ~50K tokens per drill that should not be paid.

### Streaming progress — per subagent return, not fixed cadence

Emit one line per subagent return: `Drilled <name> (<n>/<N>)`. Do not wait for fixed batches of N — subagents finish out of order, so cadence-based emits arrive in clumps. Per-return updates keep the user informed in real time.
### Filter at the API surface

Before calling `list_tasks`, push every filterable field server-side: `status`, `task_type`, `assignee_id`, `report_ids`, `name_contains`. The MCP applies these at the source and returns a smaller payload. Filter in-script only what the API can't handle. Reference: `automatically-draft-flux-explanations` already filters by `assignee_id` + `task_type=flux` server-side — apply the same rigor here.
### Cap parallel API calls at 3

Empirical finding from perf testing: when 5+ heavy MCP calls (`query_transaction_lines`, `get_task_events`, etc.) are in flight simultaneously, three of them stall at near-identical 244–253s — suggesting rate-limit or queue contention at the MCP server. Cap simultaneous calls at 3. When fanning out N>3 units, batch by 3: dispatch 3 subagents per Agent message, await, dispatch the next 3.
