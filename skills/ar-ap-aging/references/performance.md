# Performance patterns — ar-ap-aging

The high-volume regime in Step 3 (chunked month-by-month pulls) drives most of the runtime. Apply these patterns in order.

## Fan out the chunked monthly pulls

When the first 12-month pull returns the 10K-row cap or times out, switch to the high-volume strategy. Dispatch one subagent per month (12 subagents) in a single Agent tool message. Each subagent calls `query_transaction_lines` with that month's window and returns a TSV file path. The parent dedupes by line `id` across all returned files.

In environments without subagents, walk back month by month sequentially but still write each month's TSV to the cache below.

## Keep aggregation in the bundled script

Aggregation, FIFO matching, and bucket assembly live in `scripts/build.py`. Pass the merged TSV plus a config JSON. Avoid loading the full transaction set into context.

## Materiality is N/A — never filter

Aging needs every open item. Offer a "top 50 exposures" tab as a follow-up after the workbook is delivered, not as a pre-filter.

## Default to a 12-month lookback; widen only when reconciliation forces it

Twelve months covers normal DSO/DPO and slow-pay scenarios. Surface the reconciliation gap from Step 5; do not silently widen. If the gap is material, ask via `AskUserQuestion` whether to pull a wider window or accept the gap and recommend the user pull NetSuite's native aging.

## Checkpoint per month

Each subagent writes its monthly TSV to `outputs/.aging_cache/{account_id}/{as_of_date}/{YYYY-MM}.tsv`. The parent merges from disk. Re-runs (e.g., user wants different bucket boundaries) skip the data pull entirely and re-run only `build.py`.

## Validate scope before fan-out

Before launching chunked monthly pulls, confirm:
- Mode (AR vs. AP) is explicit.
- The selected GL account exists in `list_financial_accounts` and matches the trade pattern.
- The as-of date is a real period end.
- The first single-month probe returned data (not all-empty).

A wrong account or as-of date wastes 12 monthly pulls.

## Short-circuit on empty

If the first probe returns 0 transactions for the chosen account, tell the user the account has no activity in the lookback window and stop. Do not produce an empty aging.

## Stream progress during fan-out

Emit a one-line update every monthly chunk (`"Pulled 4 of 12 months..."`).

## Subagent prompt shape

Each subagent (in high-volume regime) receives:
- `report_id`, the row key, the month's window_start/window_end, the cache path.

Each subagent returns:
- `{month: <YYYY-MM>, tsv_path: <path>, line_count: <int>}`.

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
