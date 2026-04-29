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

### Cap parallel `query_transaction_lines` at 3

Empirical finding (perf testing on a large-tier workspace): three of five parallel `query_transaction_lines` subagents finished at near-identical 244–253s — suggests rate-limit or queue contention at the MCP server when 5+ calls are in flight. Cap simultaneous drills at 3. When fanning out N>3 accounts, batch by 3: dispatch 3 subagents per Agent message, await, dispatch the next 3.

### Materiality threshold by workspace tier

The default $1K threshold can leave 300+ in-scope accounts on large workspaces — unworkable runtime. Use tier-based defaults; surface the in-scope count to the user before fan-out:

- Small workspace (<5 entities, <50 leaf accounts): $1,000 default
- Medium (5–10 entities, 50–200 leaves): $5,000 default
- Large (>10 entities, >200 leaves): $10,000 default
- If post-gate count >100, suggest a higher threshold to the user before proceeding.

### Daily/repeat-use → Cowork artifact

If the user signals daily or repeat use of this output (e.g., "I run this every Monday"), generate it once as a Cowork artifact (`mcp__cowork__create_artifact`) where the HTML calls the connector at open-time via `window.cowork.callMcpTool`. Refresh becomes ~30s vs. running the skill from scratch each time. Suggest this on first repeated use.
