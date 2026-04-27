---
name: automatically-draft-flux-explanations
description: >
  Drafts flux explanations for all GL accounts assigned to the current user in Numeric
  where a flux explanation has been requested. Loops through each in-scope task, pulls
  transaction lines from Numeric, and posts concise first-pass drafts back to Numeric.
  Trigger whenever anyone asks to "write my flux explanations", "draft flux", "do my flux",
  "run flux analysis", "flux drafts for this month", "write flux for close", "draft all
  my fluxes", "flux explanations for this period", or any reference to batch-drafting
  flux explanations in Numeric for the monthly close.
---

# write-flux-explanations

## Setup

1. **Workspace:** If the user specifies a workspace, use it. If not, ask.
2. **Flux report:** If the user specifies a report, use it. If not, `list_reports()` and ask which flux report to use.
3. `set_workspace` → `get_workspace_context` → note open period, current user, period_id
4. `list_tasks(period_id, assignee_id, task_type="flux", include_description=true)` → filter to PENDING tasks where current user is preparer

## Loop over each PENDING task (IS first, then BS)

1. **Pull 6 months of transaction lines** (current + 5 prior) using `query_transaction_lines` per month
2. **Group by available dimensions** (vendor, customer, department, class, location) — use whatever's populated, ignore what's missing
3. **Check prior period explanation** via `get_flux_explanations` for tone reference
4. **Draft the explanation** (see format below)
5. **Check for existing content** via `get_flux_explanations` on current period — if content exists, append with `---` divider. Never overwrite.
6. **Show draft to user**, then post via `update_flux_explanation`

## Draft format

**Conclusion first.** One sentence: total variance, primary driver (department/vendor/customer), concentration.
Then all supporting points as bullets.

**Example** (5105 - Employee Wages, Mar 2025):

```html
<p>The $496k MoM increase (12.4%) is driven entirely by Marketing department bi-weekly payroll for full-time employees, which accounts for 100% of activity in this account across all 6 months.</p><ul><li><strong>$496k</strong> Marketing payroll rose from $4,005k in Feb to $4,500k in Mar.</li><li>Mar at <strong>$4,500k</strong> is 79% above the 6-month average of <strong>$2,515k</strong>. The account ramped sharply from a Dec low of $1,112k through Jan ($2,225k) and Feb ($4,005k).</li><li>Average monthly increase over Oct–Mar: $622k. March's $4,500k implies $54.0M annualized, up from the Oct–Dec average of $1,453k/month ($17.4M annualized).</li></ul>
```

**RTE formatting.** The flux explanation field is a rich text editor. Post content as HTML: use `<p>` for paragraphs, `<ul><li>` for bullets, and `<strong>` for bold amounts. Do not post plain text or markdown.

**For BS rollforward accounts** (prepaid, fixed assets, accrued liabilities, deferred revenue):
replace driver bullets with Opening → +/- activity by vendor/customer → Ending.

**Where data supports it**, also include: YoY comparison, run-rate implication, % of revenue for variable costs.

## Parallelization

When drafting more than one account, fan out one agent per account after completing setup. Each agent receives: report_id, period_id, row key, report row data (prior/current/variance), and the draft format rules. Each agent independently pulls 6 months of transaction lines, analyzes, and returns the draft text. Collect all drafts, show to user, then post in parallel.

## Rules

- **Only state what the transaction data shows.** No speculation about headcount, org changes, one-time vs recurring, or anything not in the GL lines.
- Use plain dollar format for amounts (e.g. $496k, $4,500k) — no brackets. Cover 90%+ of the MoM variance.
- Baseline comparison: current period vs 6-month average first, then work backwards.
- No account overview sentences, no preparer notes, no missing-data callouts.
- Preparer's PENDING tasks only. Never post to submitted tasks.
- Check task Description for `## Flux Template` overrides (Grouping, Ignore, Context, Format).
- `update_flux_explanation` may not return a response body on success — treat a non-error call as successful and continue.

## Learning from user adjustments

When the user edits a draft before approving it, capture what changed. Ask: "Should this apply to just this account going forward, or to all accounts?"

- **Task-specific**: Append the adjustment as a `## Flux Template` override in that task's description via `edit_task`. This carries forward to the next period automatically for that account.
- **Global**: Note the adjustment in this skill's rules for the remainder of the session, and suggest the user update the skill file permanently.

Examples of adjustments worth capturing: preferred grouping dimension, vendors to ignore, context about known one-time items, formatting preferences, level of detail.

## End of run

```
-- Flux Draft Run Complete --
Period: [PERIOD NAME] | Preparer: [USER NAME]
Drafted & posted: X | Skipped (submitted): X
```
