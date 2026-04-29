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
