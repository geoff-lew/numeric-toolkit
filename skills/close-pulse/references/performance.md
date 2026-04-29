# Performance patterns — close-pulse

This skill is short by design but can run long on large workspaces with many flux/recon tasks. Apply these patterns when the task count exceeds ~100.

## Cache cold-start calls within the session

`get_workspace_context` and `list_reports` are called every run. Cache them to `outputs/.numeric_session_cache/{workspace_id}.json` after the first call, and read from cache on subsequent runs in the same session. Stale beyond ~24 hours.

## Fan out lens computations

The five lenses (materiality, urgency, progress, pace, dependencies) are independent reads of the same task list. When all five are requested, dispatch one subagent per lens in a single Agent tool message. Each lens returns a small JSON. Merge in the parent. Avoid sequentially walking the same task data five times.

In environments without subagents, run lenses sequentially.

## Default to a single-period scope

The skill is per-period by design. If the user requests multi-period or trend analysis, escalate to `close-retro` rather than expanding `close-pulse`'s scope.

## Skip lenses with no signal

If `materiality flags = 0`, `dependencies = none`, etc., omit those lens sections from the output rather than rendering empty headers.

## Daily users — convert to a Cowork artifact

If the user runs `close-pulse` daily, generate it once as a Cowork artifact (`mcp__cowork__create_artifact`) where the HTML calls the connector at open-time via `window.cowork.callMcpTool`. Refresh becomes ~10 seconds vs. running the skill from scratch each morning. Suggest this on first repeated use.

## Validate scope before computing lenses

Before computing any lens, confirm:
- The `period_id` exists in `get_workspace_context`.
- `list_tasks` returned >0 tasks for the period.

A wrong period produces empty lens output that wastes a re-run.

## Short-circuit on empty

If `list_tasks` returns 0 tasks, tell the user the period has no activity and stop. Do not render an empty dashboard.

## Stream progress when computing lenses

When all five lenses are requested, emit a one-line update per lens (`"Computed 2 of 5 lenses..."`).

## Subagent prompt shape

When fanning out lenses, each subagent receives:
- The task list path, the lens name, the materiality threshold (if any), the cache path.

Each subagent returns:
- `{lens, json_path: <file>, headline_metric}`.

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
### Filter at the API surface

Before calling `list_tasks`, push every filterable field server-side: `status`, `task_type`, `assignee_id`, `report_ids`, `name_contains`. The MCP applies these at the source and returns a smaller payload. Filter in-script only what the API can't handle. Reference: `automatically-draft-flux-explanations` already filters by `assignee_id` + `task_type=flux` server-side — apply the same rigor here.
