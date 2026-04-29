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

### Daily/repeat-use → Cowork artifact

If the user signals daily or repeat use of this output (e.g., "I run this every Monday"), generate it once as a Cowork artifact (`mcp__cowork__create_artifact`) where the HTML calls the connector at open-time via `window.cowork.callMcpTool`. Refresh becomes ~30s vs. running the skill from scratch each time. Suggest this on first repeated use.
