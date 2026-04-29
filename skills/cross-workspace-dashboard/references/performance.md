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
