# Performance patterns — dept-anomaly-scan

Steps 3 and 4 dominate runtime: flagging anomalies on a wide pivoted report, then drilling into each one with `query_transaction_lines`. Apply these patterns in order.

## Fan out the per-anomaly drill

Step 4's drill is per flagged row and each drill is independent. After applying the materiality gate, dispatch one subagent per anomaly in a single Agent tool message. Each subagent receives `report_id`, the anomaly's row key, the date window, and the rule that flagged it. Each returns the transaction sample plus a one-line root-cause summary. Merge in the parent.

In environments without subagents, run sequentially but keep the script-first, materiality-gate, and checkpoint patterns.

## Push the anomaly aggregation to a script

Use `scripts/aggregate_anomalies.py` to take the report TSV plus the rule set and emit a JSON list of `[{account, department, amount, rule_triggered, prior_month_amount}, ...]`. Inline pivot reasoning over a department × account matrix wastes context.

## Apply a materiality gate before drilling

Filter flagged rows before fan-out:

- Default: skip anomalies with absolute amount < $5,000.
- Always keep "new large items" (prior=$0, current>$10K) regardless of size.
- Show the user the count of anomalies in vs. out of scope and let them override.

Drilling into immaterial anomalies adds runtime without changing the reclass list.

## Default to a 6-month report window; bound drill windows tightly

`month_over_month_6` is the report comparison default. Confirm via `AskUserQuestion` before widening to 12 months. Drill windows should be the as-of month plus the prior month only — not the full report window.

## Checkpoint per anomaly

Each subagent writes its drill output to `outputs/.dept_anomaly_cache/{account}_{department}_{period_id}.json` before returning. Re-runs read from cache. The reclass CSV builder in Step 5 reads from the same cache.

## Validate scope before drilling

Before fanning out to `query_transaction_lines`, confirm:
- The chosen report has department dimension data (the row paths contain named functional areas).
- The selected period exists and contains data for the report.
- `aggregate_anomalies.py` produced >0 anomalies after the materiality gate.

A pivot-less report or empty period wastes the entire drill loop.

## Short-circuit on empty

If `aggregate_anomalies.py` returns 0 anomalies after the materiality gate, tell the user no anomalies cleared the threshold and stop. Do not fan out. Do not generate a reclass CSV with no entries.

## Stream progress during fan-out

Emit a one-line update **after each subagent returns** (e.g., `"Drilled <account>/<department> (5/47)"`). See "Streaming progress — per subagent return, not fixed cadence" below for the canonical rule.

## Subagent prompt shape

Each subagent receives, as inputs only:
- `report_id`, the anomaly's row key, `window_start`/`window_end` (as-of month + prior month), the rule that flagged it, the cache path.

Each subagent returns:
- `{account, department, rule, drill_path: <json file>, root_cause: <one line>}`.

Subagents have no conversation history. Pass everything they need as inputs.
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
### Cap parallel API calls at 3

Empirical finding from perf testing: when 5+ heavy MCP calls (`query_transaction_lines`, `get_task_events`, etc.) are in flight simultaneously, three of them stall at near-identical 244–253s — suggesting rate-limit or queue contention at the MCP server. Cap simultaneous calls at 3. When fanning out N>3 units, batch by 3: dispatch 3 subagents per Agent message, await, dispatch the next 3.
### Materiality threshold by workspace tier

Tier-based defaults; surface the in-scope count to the user before fan-out and let them override:

- Small workspace (<5 entities): default threshold per the skill's primary materiality rule
- Medium (5–10 entities): 5× the small default
- Large (>10 entities): 10× the small default
- If post-gate count >100 units, suggest a higher threshold to the user before proceeding.
