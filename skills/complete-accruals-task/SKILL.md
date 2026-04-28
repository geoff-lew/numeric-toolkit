---
name: complete-accruals-task
user-invocable: true
description: >
  Completes an accrual task in Numeric end-to-end: analyzes vendor spend history,
  identifies accrual candidates using configurable triggers, generates an Excel
  workpaper and NetSuite-ready CSV journal entries, posts task comments, and
  submits the task. Saves preferences (vendor overrides, exclusions, criteria)
  into the task description so they carry forward to the next period automatically.
  Trigger whenever the user mentions "complete accruals", "accrual task",
  "run accruals", "do the accruals", "software accruals", "expense accruals",
  "complete the accrual task", "accrue vendors", "monthly accruals",
  "accrual workpaper", "which vendors to accrue", or any reference to completing
  a Numeric checklist task that involves identifying vendors to accrue for and
  generating accrual journal entries.
---

# Complete Accruals Task

Completes a Numeric accrual task: pulls transaction history, identifies accrual candidates, gets user confirmation, generates workpaper + JE CSV, submits the task with structured comments, and saves preferences to the task description for next month.

The task name or description is: $ARGUMENTS

---

## Step 0: Load workspace + context

**0a. ToolSearch — batch upfront**
Before any API calls, load all tool schemas you will need in a single ToolSearch call:
`list_workspaces, set_workspace, get_workspace_context, list_tasks, list_financial_accounts, query_transaction_lines, submit_task, add_task_comment, edit_task`

**0b. Workspace check**
Check memory for `workspace_id`. If found, call `set_workspace` directly; do NOT call `list_workspaces`.

If no saved workspace, call `list_workspaces`, ask the user which one to use, then call `set_workspace`. Save the chosen workspace to memory.

**0c. Parallel cold-start**
Immediately after `set_workspace` resolves, fire all three calls IN PARALLEL:

- **`get_workspace_context`**
- **`list_financial_accounts`**
- **`list_tasks`**

---

## Step 0.5: Default preferences

These defaults apply when no preferences are found in the prior period's task description (step 1.5a) and the current task description does not specify its own criteria. Any preferences loaded from a prior period or parsed from the task description override these.

**Default triggers** (what makes a vendor a candidate):
- Vendor has $0 in the open period AND >$0 in the most recent completed month
- Vendor has $0 in both the open period and the most recent completed month, but had >$0 spend in at least 3 of the prior 5 completed months
- No minimum spend threshold (all amounts qualify)

**Default estimation methods** (applied in priority order per vendor):
1. >=6 months of non-zero data: 6-month rolling average of the most recent 6 completed months
2. >=3 months of non-zero data: 3-month rolling average of the most recent 3 completed months
3. 1-2 months of data: most recent non-zero month as a proxy
4. No historical data: flag as "estimate needed" — ask the user for a good-faith amount

**Default exclusions:** None. All vendors matching a trigger are presented to the user for confirmation.

---

## Step 1: Find the task + confirm entity

From the `list_tasks` result, fuzzy-match the task whose name best fits `$ARGUMENTS`.

From `get_workspace_context`, note:
- The currently **open** period (status = "open")
- All entities and their internal IDs

Present to the user in a single message:
- The matched task name and description (confirm it's the right one)
- If the workspace has more than one entity and the task description doesn't specify one: ask which entity to scope to

Wait for the user to confirm the task and entity before proceeding. Do NOT fire `query_transaction_lines` yet — wait until the task and entity are confirmed to avoid wasted API calls on a mismatch.

---

## Step 1.5: Load preferences from prior period + manual vendor check

**1.5a. Load saved preferences**
Search the `list_tasks` results for a matching task in the most recently **closed** period (same task name or close variant). If found, read its task description and look for a `## Accrual preferences` section appended by a prior run. If present, parse:
- `vendor_overrides`: per-vendor method overrides (e.g. "use prior month instead of 6-month avg")
- `vendor_exclusions`: vendors explicitly excluded and why
- `criteria_overrides`: any thresholds or trigger rules the user adjusted

Tell the user which preferences are being carried forward from the prior period. If no prior task or no preferences section is found, proceed with the defaults defined in step 0.5.

**1.5b. Manual vendor check**
Ask in the same message:

"Are there any vendors to accrue for manually? Specifically: (a) vendors you've purchased from but haven't received a bill for yet, or (b) vendors where a bill for the prior month is known to be incoming. For each, provide the vendor name and a dollar amount (or basis for estimating one)."

If the user provides manual vendors, carry them forward into step 5.5. If none, proceed.

---

## Step 2: Parse the task instructions

Read the task description carefully and extract the following. **The task description always takes precedence over defaults.**

**2a. Account**
Identify the account to analyze (e.g. "software expense", "consulting expense").

**2b. Entity scope**
Use the entity confirmed in step 1. Resolve it to an internal ID from the workspace context.

**2c. Accrual triggers** — what makes a vendor a candidate
Parse any explicit criteria from the task description. Common patterns to look for:
- Minimum spend threshold (e.g. "only accrue for expenses >$10,000")
- Zero-spend condition (e.g. "vendors where we have spent $0 this month")
- Month-over-month change threshold (e.g. "|MoM| > 500%")
- Any other vendor-selection rules

If the task description does not specify triggers, use the default triggers from step 0.5. Flag to the user that defaults are being used.

Apply any `criteria_overrides` loaded from the prior period's task description (step 1.5a) on top — these take precedence over defaults but are overridden by anything explicit in the current task description.

**2d. Accrual estimation method** — how to size each accrual
Parse any explicit method from the task description (e.g. "use 6-month rolling average", "use prior month", "use fixed amount $X").

If the task description does not specify a method, use the default estimation methods from step 0.5. Flag to the user that defaults are being used.

**Important**: Apply the minimum spend threshold (if any) to the **most recently observed non-zero monthly spend**, not to the calculated average. A vendor whose average is suppressed by historically low months but whose recent spend exceeds the threshold should still be included.

Apply any `vendor_overrides` loaded from the prior period's task description (step 1.5a) on top of the default method for specific vendors — these set per-vendor method overrides (e.g. "use prior month for Vendor X"). Tell the user which overrides are active.

---

## Step 3: Find the account

Use the `list_financial_accounts` result from step 0c. Match the account name from the task description. Note its `external_id` and full name.

Also identify the **Accrued Expenses** liability account (typically code 2300 or similar). Note its `external_id` and account number.

---

## Step 4: Pull transaction lines and build spend matrix

Now that the task, entity, and account are confirmed, issue a **single** `query_transaction_lines` call covering the full 7-month window — the 6 completed months plus the open period:
- `key`: `{"id": "<account_external_id>", "type": "path"}`
- `window_start`: first day of the oldest completed month (6 months before the open period)
- `window_end`: last day of the open period

This gives 6 completed months of history plus the open period for current spend. Do not make two separate API calls.

**If the result is too large for context** (saved to a tool-results file), use the bundled script to parse it:

```bash
python3 <skill_path>/scripts/parse_txn_lines.py <tool_results_file> <working_dir>/vendor_spend_matrix.json --entity-org-id <org_id>
```

The script handles the JSON-wrapped TSV format, filters by entity, groups by counterparty × posting month, and outputs a clean JSON matrix. If the result fits in context, you can still use the script or parse inline — but the script is faster and avoids re-deriving the column names and date parsing logic.

The output `vendor_spend_matrix.json` has this structure:
```json
{
  "vendors": { "Vendor Name": { "YYYY-MM": amount, ... }, ... },
  "months": ["YYYY-MM", ...],
  "entity_filter_applied": "org_id=1",
  "total_rows_parsed": N,
  "total_rows_after_filter": N
}
```

---

## Step 5: Identify candidates and present for selection

Use the bundled script to identify accrual candidates:

```bash
python3 <skill_path>/scripts/identify_candidates.py \
    <working_dir>/vendor_spend_matrix.json \
    <working_dir>/accrual_candidates.json \
    --open-period <YYYY-MM>
```

If prior-period preferences included vendor exclusions, pass them as a comma-separated list:
```bash
    --exclusions "Vendor A,Vendor B"
```

The script applies the default triggers from step 0.5, identifies candidates and Section B observations, and outputs:
- `accrual_candidates.json` — candidates, observations, and a pre-formatted markdown table
- **stdout** — the markdown table, ready to paste into your response

**Manual vendors from step 1.5b**: If the user provided manual vendors, append them to the candidates list in `accrual_candidates.json` before presenting, with trigger = "Manual — unbilled purchase / expected prior-month invoice" and the user-provided amount as the proposed accrual.

**Present to the user**: Show the markdown table directly in your message — no file, no link. The table has numbered rows so the user can reply with just the numbers. Follow it with:

"Which vendors should I accrue for? Reply with the numbers, or adjust any amounts/methods."

**If no candidates**: Tell the user "No accrual candidates identified for this period." Ask whether to submit with a $0 accrual note or investigate further.

Wait for the user's response. Only proceed with the vendors the user explicitly confirms. Apply any method or amount overrides they request — these will be saved to the task description in step 9.

---

## Step 6 + 7: Generate workpaper, JE CSV, and validation

Once the user confirms which vendors to accrue for, prepare two JSON files:

**confirmed_vendors.json** — array of the selected vendors:
```json
[
  {
    "vendor": "Vendor Name",
    "method": "6-mo avg",
    "method_detail": "6-month avg of (Nov $X + Dec $Y + Jan $Z)",
    "proposed_amount": 1234.56,
    "trigger": "$0 in Mar, $5,000 in Feb"
  }
]
```

**excluded_vendors.json** (optional) — vendors the user declined:
```json
[
  { "vendor": "Vendor B", "proposed_amount": 5000.00, "reason": "User chose not to accrue" }
]
```

Then run the bundled output generator:

```bash
python3 <skill_path>/scripts/generate_outputs.py \
    --spend-matrix <working_dir>/vendor_spend_matrix.json \
    --confirmed-vendors <working_dir>/confirmed_vendors.json \
    --output-dir <output_dir> \
    --period-slug <period-slug> \
    --period-end <M/DD/YYYY> \
    --open-period <YYYY-MM> \
    --expense-acct-code <code> \
    --expense-acct-name "<full name>" \
    --accrued-exp-acct-code <code> \
    --entity-id <id> \
    --excluded-vendors <working_dir>/excluded_vendors.json
```

This single command produces all three output files:

**Workpaper** (`{slug}_accrual_workpaper_{period}.xlsx`) — 3 sheets:
- Sheet 1: all vendors × 6 months, accrual candidates highlighted yellow, SUM totals, frozen panes
- Sheet 2: accrual detail (confirmed vendors only) with avg and memo
- Sheet 3: Numeric tab with accrued expenses account, entity ID, and formula linking to Sheet 2 total

**JE CSV** (`{slug}_journal_entries_{period}.csv`) — NetSuite-ready import with one debit + credit line per vendor. Memo includes both the calculation and the trigger.

**Validation** (`{slug}_accrual_validation_{period}.txt`) — candidate summary, excluded vendors, and DR=CR balance check. The script runs the balance check automatically and reports PASS/FAIL.

The script requires `openpyxl` — if not installed, it will print the install command and exit.

**7b. Check for NetSuite MCP availability**
Check whether `ns_createRecord` is available in the current tool list.

If **yes**:
- Ask the user: "NetSuite MCP is available. Should I post these journal entries directly to NetSuite?"
- If confirmed, post journal entries using `ns_createRecord` with type `journalentry`. For multi-entity workspaces, use the entity's NetSuite subsidiary ID. Capture the NetSuite internal ID returned for each JE.
- **Error handling:** If a post fails for a specific vendor, log the error, skip that vendor, and continue posting the remaining entries. After the batch completes, report which entries succeeded (with NetSuite IDs) and which failed (with error details). Ask the user how to handle failures — retry, post manually via CSV, or skip.
- Add the NetSuite JE IDs to the memo column in Sheet 2 of the workpaper and to the task comment.
- The CSV is still saved as a backup artifact.

If **no**:
- Proceed with CSV only. Note in the task comment that entries are ready for manual import.

After generating all outputs, ask: "Ready to submit the task in Numeric?"

---

## Step 8: Submit the task in Numeric

Only after the user confirms:
1. Check the `list_tasks` output to confirm the authenticated user is the **preparer** (ASSIGNEE) on this task. If they are the reviewer instead, offer to swap assignee/reviewer roles before submitting.
2. Before calling `submit_task`, post **two separate comments** via `add_task_comment`. Use `•` bullets with a blank line between each bullet (double newline). Do not use HTML or markdown — the API treats them as literal text.

**Comment 1 — Journal entries (post this first):** One bullet per vendor. Format:
```
• $X,XXX for [Vendor] using [method description].

• $X,XXX for [Vendor] using [method description].
```
If posted to NetSuite, add the JE ID after the method description.

**Comment 2 — Total + observations (post this second, so it appears on top):** Total as the first bullet, followed by one bullet per observation, each separated by a blank line. Format:
```
• Total accrual: $X,XXX.

• [Observation one.]

• [Observation two.]
```
Examples of observations worth including:
- A vendor included despite being below the spend threshold
- An excluded vendor that might surprise the reviewer
- A vendor that went to zero and may be cancelled
- A vendor where the accrual method was overridden and why

Always post Comment 2, even if there are no observations — the total line must always appear. Only add observation bullets when there is something genuinely worth flagging. Do not include observations just to be thorough.

3. Call `submit_task` with `role: ASSIGNEE`.

---

## Step 9: Save preferences to task description

Use `edit_task` to **append** an `## Accrual preferences` section to the existing task description. Do NOT overwrite the existing description content — read the current description and append the new section at the end, separated by a blank line.

If an `## Accrual preferences` section already exists in the description (e.g. from a prior run or manual edit), replace only that section and leave everything above it intact.

The appended section should follow this format:

```
## Accrual preferences
Last run: {YYYY-MM period slug}

### Vendor overrides
- {Vendor}: use {method} (reason: {why the override was applied})
- ...

### Vendor exclusions
- {Vendor}: excluded (reason: {why})
- ...

### Criteria overrides
- min_accrual_amount: {amount, if non-default}
- custom_triggers: {any non-default triggers from the task description or user adjustments}
```

Only include subsections that have content. If there are no vendor overrides, omit that subsection entirely. The goal is a clean, human-readable block that a reviewer can scan and that the next run can parse.

Tell the user: "Preferences saved to the task description. Next month, overrides and exclusions will carry forward automatically from this period's task."
