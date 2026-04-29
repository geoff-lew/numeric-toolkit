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
### Filter at the API surface

Before calling `list_tasks`, push every filterable field server-side: `status`, `task_type`, `assignee_id`, `report_ids`, `name_contains`. The MCP applies these at the source and returns a smaller payload. Filter in-script only what the API can't handle. Reference: `automatically-draft-flux-explanations` already filters by `assignee_id` + `task_type=flux` server-side — apply the same rigor here.
