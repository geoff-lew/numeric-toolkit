# Performance patterns — complete-accruals-task

This skill is mostly fast — it issues one big `query_transaction_lines` call and runs scripts. The improvements are around the user-confirmation loop and resuming partial runs.

## Single big call already, no fan-out needed

Step 4's combined 7-month window is correct. Do not split it. The cost driver is in-context parsing of the response when it doesn't fit; `scripts/parse_txn_lines.py` handles that. Use it.

## Confirm window upfront

The 7-month window (6 completed + open) is the default. If the user implies a longer history ("longer history", "annualize"), ask via `AskUserQuestion` whether to pull 12 months instead. Avoid silently widening.

## Checkpoint between identify and confirm

Save the candidate list from `identify_candidates.py` to `outputs/.accruals_cache/{period_id}/{task_id}/candidates.json` before presenting it. If the user steps away mid-confirmation and returns later, the next run reads the cache instead of re-pulling 7 months of transactions and re-running the trigger logic. Same for the workpaper output — checkpoint after Step 6 so a re-run after submission failure does not have to rebuild the workpaper.

## Materiality is already user-driven

The trigger thresholds in Step 0.5 and Step 2 are the gate. Do not add a second one.

## Validate scope before pulling

Before issuing the 7-month `query_transaction_lines` call, confirm:
- The matched task exists in the open period.
- The entity is confirmed (Step 1).
- The accrual account is identified in `list_financial_accounts` (Step 3).

A bad task match or wrong entity wastes the entire transaction pull.

## Short-circuit on empty

If `identify_candidates.py` returns 0 candidates and the user has no manual additions, tell the user "No accrual candidates identified for this period" and ask whether to submit with a $0 accrual note. Do not generate an empty workpaper.

## Stream progress

Emit a one-line update at each major step (`"Pulled 7 months of transactions..."`, `"Identified 12 candidates..."`, `"Generated workpaper..."`).
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
