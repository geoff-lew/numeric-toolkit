# Performance patterns — executive-report

The multi-entity branch drives most of the runtime. Apply these patterns in order.

## Fan out per entity

For multi-entity executive reports, dispatch one subagent per entity in a single Agent tool message. Each subagent pulls its IS and BS via the routing rule in Step 1, runs the executive group collapse, and returns normalized JSON: `{entity, period, groups: [{group_name, value, prior_value}, ...]}`. The parent merges into the consolidated view and writes the workbook. For 5+ entities this is the largest single speedup.

In environments without subagents, run sequentially but still cache per entity.

## Push the group collapse to a script

Use `scripts/collapse_to_groups.py` to take the IS/BS TSV plus the chart of accounts JSON and emit the executive-group rollup. The script handles single-entity and per-entity invocations. Inline group mapping over the full chart of accounts wastes context per entity.

## Materiality is structural, not numeric

Executive groups are pre-defined; do not skip groups even when small. For flux narrative rollup, apply the existing >5% / >$10K threshold strictly — generate one-line narratives only for material movers.

## Window — period-bound; confirm comparison

Single period or comparison is a common ambiguity. Ask via `AskUserQuestion` upfront: prior month, prior quarter, prior year, budget vs. actual, or none. Avoid pulling comparison-period data until confirmed.

## Checkpoint per entity

Each subagent writes its rollup to `outputs/.exec_report_cache/{period_id}/{entity_id}.json` before returning. The workbook builder reads from cache. Re-runs for a different output format or comparison skip the data pull and only re-render.

## Validate scope before fan-out

Before fanning out per entity, confirm:
- Each `entity_id` has matching IS and BS saved configurations (or a justified `build_report` fallback).
- The `period_id` is open or closed (not in-flight if the user wants a clean snapshot).
- The comparison choice is confirmed via `AskUserQuestion`.

A missing per-entity report or unconfirmed comparison produces an inconsistent consolidated view.

## Short-circuit on empty

If 0 entities have viable saved IS/BS configs and `build_report` fallback isn't approved, tell the user and stop. Do not produce a partial multi-entity workbook.

## Stream progress during fan-out

Emit a one-line update per entity (`"Collapsed 3 of 7 entities..."`).

## Subagent prompt shape

Each subagent receives:
- `entity_id`, the `period_id`, the IS and BS `configuration_id`s for that entity, the comparison setting, the cache path, the path to `collapse_to_groups.py`.

Each subagent returns:
- `{entity_id, rollup_path: <json file>, revenue, gross_profit, net_income, group_count}`.

Subagents have no conversation history.
