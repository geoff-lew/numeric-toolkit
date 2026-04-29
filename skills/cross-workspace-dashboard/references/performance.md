# Performance patterns — cross-workspace-dashboard

This skill scales linearly with workspace count: N workspaces × all the close-pulse work per workspace. Apply these patterns in order.

## Fan out per workspace

Workspaces are independent. Dispatch one subagent per workspace in a single Agent tool message. Each subagent calls `set_workspace`, pulls task and event data, runs the per-workspace aggregation script, and returns a normalized JSON summary. Merge in the parent. For 5+ workspaces this is the largest single speedup.

In environments without subagents, run sequentially but still cache per workspace.

## Push per-workspace aggregation to a script

Use `scripts/aggregate_workspace.py` to take the raw task TSV plus event JSON for one workspace and emit the dashboard inputs (completion %, late count, materiality flags, sole-reviewer warnings). Each subagent invokes the script after fetching.

## Skip workspaces with no activity

Before fanning out, ask via `AskUserQuestion` whether to include workspaces with no in-period activity. They appear as "100% complete, 0 tasks" and add noise. Default: skip but list in a footer.

## Confirm period scope

"All entities, this close" is ambiguous when entities are on different close calendars. Ask upfront: same period across all, or each entity's most recent open period. Default to same period.

## Checkpoint per workspace

Each subagent writes its summary to `outputs/.cross_workspace_cache/{period_id}/{workspace_id}.json`. Re-runs read from cache. For daily use, only re-fetch workspaces whose cache is older than today.

## Daily users — convert to a Cowork artifact

If the user runs this dashboard daily, generate it once as a Cowork artifact (`mcp__cowork__create_artifact`) where the HTML calls the connector at open-time via `window.cowork.callMcpTool`. A 3-minute generation becomes a 30-second refresh on each open. Suggest this on first use.

## Validate scope before fan-out

Before fanning out per workspace, confirm:
- Each requested `workspace_id` is reachable from `list_workspaces`.
- The period scope is confirmed (same period across all entities, or each entity's most recent open period).
- The empty-workspace skip rule is confirmed.

A typo in a workspace ID or unconfirmed period scope wastes the entire fan-out.

## Short-circuit on empty

If after the empty-workspace skip the in-scope workspace count is 0, tell the user and stop. Do not generate a dashboard with no rows.

## Stream progress during fan-out

Emit a one-line update every workspace (`"Aggregated 3 of 12 workspaces..."`).

## Subagent prompt shape

Each subagent receives, as inputs only:
- `workspace_id`, `period_id`, the path to `aggregate_workspace.py`, the cache directory, the as-of date.

Each subagent returns:
- `{workspace_id, summary_path: <json file>, total_tasks, completion_pct, late_count}`.

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
