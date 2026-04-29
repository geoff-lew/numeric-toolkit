# Performance patterns — report-txn-detail

This skill issues one `query_transaction_lines` call per drillable account on the report — often 50+ calls. Apply these patterns in order.

## Fan out the per-account drill

Drillable accounts from Step 3 are independent units. After applying the materiality gate below, dispatch one subagent per account in a single Agent tool message. Each subagent receives `report_id`, the row's `key`, `window_start`, `window_end`, and the report group label. Each returns its TSV file path. Merge in the parent. Avoid sequential loops.

In environments without subagents (e.g., Claude.ai), run sequentially but still apply the script-first, materiality-gate, and checkpoint patterns below.

## Push report parsing to a script

Use `scripts/parse_report.py` to read the report TSV from disk and emit a small JSON of `[{account_name, key, type, group, balance}, ...]`. Inline TSV parsing in the main loop wastes context and serializes the run.

## Apply a materiality gate before drilling

Filter the drillable accounts before fan-out:

- Default: skip accounts with absolute balance < $1,000 in the as-of period.
- For MoM/YTD reports: skip if absolute balance < $1,000 in every period column.
- Show the user the count of accounts in vs. out of scope and let them override (`include all`, `raise to $X`, `lower to $X`).

Material balances drive the conclusion. Drilling into immaterial accounts adds runtime without changing the read.

## Default to a narrow window; ask before widening

Step 4's window can produce 12+ months of transaction lines. Default to `single_month` unless the user explicitly asked for a comparison view. Use `AskUserQuestion` upfront to confirm the window when the request is ambiguous (e.g., "give me the IS with detail" — confirm single month vs. trailing).

## Checkpoint per account

Each subagent writes its result to `outputs/.txn_detail_cache/{account_external_id}_{period_id}.tsv` before returning. Read from cache for any account whose checkpoint already exists. A re-run after a partial failure resumes from the last completed account.

## Validate scope before fan-out

Before dispatching subagents, confirm:
- The selected `configuration_id` resolves in `list_reports`.
- The `period_id` exists in `get_workspace_context`.
- `get_report_data` returned >0 leaf rows after the materiality gate.

A bad period or empty report wastes 50+ `query_transaction_lines` calls. Surface ambiguity via `AskUserQuestion` upfront.

## Short-circuit on empty

If the materiality-gated drillable list is empty, write the report tab only (no Transaction Lines tab) and tell the user no accounts crossed the threshold. Do not fan out. Do not produce an empty workbook.

## Stream progress during fan-out

Emit a one-line update every ~10 accounts (`"Pulled detail for 20 of 45 accounts..."`). Failures surface earlier; the user has visible progress during long runs.

## Subagent prompt shape

Each subagent receives, as inputs only:
- `report_id`, the row's `key` object, `window_start`, `window_end`, the report group label, the cache path.

Each subagent returns:
- `{account: <name>, key: <key>, tsv_path: <path>, line_count: <int>}` — a small JSON, not the TSV itself.

Subagents have no conversation history. Pass everything they need as inputs. Do not assume re-derivation of period IDs, configuration IDs, or row keys.
