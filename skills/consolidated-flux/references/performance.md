# Performance patterns — consolidated-flux

Each consolidation dimension fans out independent work — entities, reports, accounts, periods. Apply these patterns in order.

## Fan out the cross-dimension pulls

- Dimension 1 (entities): one subagent per entity. Each pulls its `list_tasks`, `get_task_comments`, and `get_flux_explanations` and returns normalized JSON.
- Dimension 2 (reports): one subagent per report.
- Dimension 4 (periods): one subagent per trailing period.

Dispatch all subagents in a single Agent tool message and merge in the parent. Sequential execution across 5 entities × 4 reports is the dominant cost; this collapses it into one round-trip.

In environments without subagents, run sequentially but still apply the script-based merge and per-unit cache.

## Push the merge to a script

Use `scripts/merge_flux.py` to take the per-entity / per-report JSON outputs and produce the unified table (one row per account-group, columns per dimension). Inline merging across dimensions is brittle and slow.

## Apply a materiality rollup

When fanning out by accounts (Dimension 3), only synthesize narratives for groups whose absolute variance exceeds a threshold. Default: $10K or 5% of group total, whichever is larger. Show the user the count of groups in vs. out of scope before drafting.

## Window — period-bound

For Dimensions 1–3, the window is the target period. For Dimension 4 (trend), default to 3 trailing periods; ask via `AskUserQuestion` before extending to 6.

## Checkpoint per dimension unit

Each subagent writes its result to `outputs/.consolidated_flux_cache/{period_id}/{dimension}/{unit_id}.json` before returning. Re-runs (e.g., user re-frames the narrative) read from cache rather than re-fetching.

## Validate scope before fan-out

Before fanning out across dimensions, confirm:
- Each in-scope `entity_id` and `report_id` resolves.
- The target `period_id` exists for every entity.
- The chosen dimensions match the user's intent.

A bad entity ID or report ID wastes the entire dimension's pull.

## Short-circuit on empty

If after the materiality rollup the in-scope group count is 0, tell the user no groups crossed the threshold and stop. Do not produce an empty consolidated table.

## Stream progress during fan-out

Emit a one-line update per dimension unit (`"Pulled flux for 3 of 7 entities..."`).

## Subagent prompt shape

Each subagent receives:
- The dimension unit's identifier (entity_id, report_id, or period_id), the relevant calls to make, the cache path.

Each subagent returns:
- `{unit_id, dimension, json_path: <file>, group_count, materiality_pass_count}`.

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
