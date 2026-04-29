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

Emit a one-line update **after each batch subagent returns** (e.g., `"Pulled events for batch <n> (3/8) — 150 tasks"`). See "Streaming progress — per subagent return, not fixed cadence" below for the canonical rule.

## Subagent prompt shape

Each subagent receives, as inputs only:
- The list of `task_keys` in its batch, the user-ID-to-name map, the cache directory.

Each subagent returns:
- `{batch_index, parsed_path: <json file>, task_count, event_count}`.

Subagents have no conversation history. Pass everything they need as inputs. Do not assume access to the workspace context or the full task list.
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
