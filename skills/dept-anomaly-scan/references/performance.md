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

Emit a one-line update every ~10 drills (`"Drilled 20 of 47 anomalies..."`).

## Subagent prompt shape

Each subagent receives, as inputs only:
- `report_id`, the anomaly's row key, `window_start`/`window_end` (as-of month + prior month), the rule that flagged it, the cache path.

Each subagent returns:
- `{account, department, rule, drill_path: <json file>, root_cause: <one line>}`.

Subagents have no conversation history. Pass everything they need as inputs.
