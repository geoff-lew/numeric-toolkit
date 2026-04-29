# Performance patterns — automatically-draft-flux-explanations

Each pending flux task pulls six months of transaction lines and drafts an explanation. With more than ~5 tasks, sequential execution dominates runtime. Apply these patterns in order.

## Fan out per task

After setup, dispatch one subagent per pending task in a single Agent tool message. Each subagent receives `report_id`, `period_id`, the row key, the report row data (prior/current/variance), and the draft format rules. Each pulls its own 6 months of `query_transaction_lines`, runs the aggregation script, drafts the explanation, and returns the HTML. Collect all drafts in the parent, show to the user, then post in parallel via another batched Agent dispatch.

In environments without subagents, draft sequentially but still apply the script-first, materiality-gate, and checkpoint patterns.

## Push transaction aggregation to a script

Use `scripts/aggregate_txn_by_dimension.py` to take the 6-month transaction TSV and emit a small JSON: `{by_vendor: {...}, by_department: {...}, by_class: {...}, monthly_totals: [...]}`. Each subagent runs the script after fetching transactions, then drafts from the JSON. Inline aggregation of 6 months of TSV burns context per task.

## Apply a materiality gate

Filter the task list before fan-out:

- Default: skip flux tasks where absolute variance < $5,000 AND |variance %| < 10% (both must be true to skip).
- Show the user the count of in-scope vs. skipped tasks before fanning out and let them override.

Drafting explanations for movements below this threshold rarely changes the close narrative.

## Default to a 6-month lookback

Six months is the analytical baseline. If the user implies a deeper view ("trend", "annual"), confirm via `AskUserQuestion` before widening to 12 months — doubles the data volume per task.

## Checkpoint per task

Each subagent writes its draft to `outputs/.flux_drafts_cache/{period_id}/{task_id}.html` before returning. The post-to-Numeric step reads from cache. If the user edits one draft and wants to keep the others, only the affected task re-drafts; the rest are read from cache.

## Validate scope before fan-out

Before dispatching subagents, confirm:
- The user is the assigned preparer on the filtered tasks.
- The `report_id` resolves in `list_reports`.
- After the materiality gate, the in-scope task count is >0.

A wrong filter or wrong report wastes 6 months of `query_transaction_lines` per task.

## Short-circuit on empty

If 0 tasks remain after the materiality gate, tell the user no flux tasks crossed the threshold and stop. Do not fan out.

## Stream progress during fan-out

Emit a one-line update every ~5 tasks (`"Drafted 10 of 23 tasks..."`).

## Subagent prompt shape

Each subagent receives, as inputs only:
- `report_id`, `period_id`, the row key, the report row data (prior/current/variance), the draft format rules, the cache path.

Each subagent returns:
- `{task_id, draft_path: <html file>, summary: <one-line>}`.

Subagents have no conversation history. Pass everything they need as inputs. Do not assume access to task descriptions, prior-period explanations, or the workspace context — those must be in the inputs.
