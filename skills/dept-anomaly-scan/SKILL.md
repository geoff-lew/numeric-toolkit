---
name: dept-anomaly-scan
user-invocable: true
description: >
  Scan a Numeric workspace for GL-to-department coding anomalies and generate a
  NetSuite CSV journal entry import to reclass them. Trigger this skill whenever
  the user mentions "department anomalies", "GL miscodings", "department scan",
  "reclass", "wrong department", "vendor coded to wrong department",
  "GL accounts hitting wrong departments", "department review", "anomaly scan",
  "coding errors", "department cleanup", or any reference to finding expenses
  booked to departments where they don't belong. Also trigger when the user says
  things like "check the books for department issues", "anything miscoded",
  "run a department audit", "scan for miscodings in [workspace]", or "generate
  reclass entries". If the user mentions Numeric in the context of departments,
  vendors, GL accounts, or anomalies, use this skill.
---

# Department Anomaly Scan & Reclass

This skill connects to a Numeric workspace, systematically scans for GL accounts
and vendors booked to departments where they don't logically belong, drills into
transaction lines to confirm root causes, and produces a ready-to-import NetSuite
CSV journal entry file to fix the miscodings.

## Workflow Overview

1. **Connect** — Find and set the target workspace in Numeric
2. **Map** — Pull the chart of accounts, workspace context, and existing reports
   to understand the department and GL structure
3. **Scan** — Build or retrieve reports pivoted by Department × Account to
   identify anomalous combinations
4. **Drill** — Query transaction lines on the flagged rows to confirm root causes
   (manual journals, Ramp card defaults, accrual templates, etc.)
5. **Reclass** — Generate a balanced NetSuite CSV JE import with one entry per
   anomaly, ready for review and upload

## Step 1: Connect to the workspace

```
list_workspaces → find the workspace the user named → set_workspace
```

If the user doesn't specify a workspace, ask. If there are multiple close matches,
confirm with the user before proceeding.

## Step 2: Map the workspace structure

Pull these two things in parallel:

- `get_workspace_context` — entities (GL connection IDs), periods, users
- `list_reports` — all report configurations

The results will often be large. Use `jq` or Python to extract what's needed:

- **Entities**: note the `id` field — the prefix before the `/` is the `gl_connection_id`
  needed for `build_report` (only required if the user selects the ad-hoc option in Step 3)
- **Periods**: sort by end date descending; identify the most recent closed period
  (the primary analysis month)
- **Reports**: extract all income statement reports that are not deleted — present
  the full list to the user in Step 3

Only call `list_financial_accounts` if the user selects the ad-hoc report option
in Step 3 and the GL structure is needed to configure the pivots.

## Step 3: Scan for anomalies

### Selecting the report

From the `list_reports` results, extract all income statement reports that are not
deleted. Present them to the user as a simple numbered list in the chat — all of
them, not just the ones with department pivots configured. The user knows their
workspace and which report contains department data; let them choose.

Always include "Build ad-hoc report" as the final option, and label it as a last resort
(`build_report` is unreliable and frequently returns empty data — prefer any saved report
where department data exists, even if its name isn't a perfect fit).

Ask the user to pick one before proceeding.

### Validating the selected report

Once the user picks a report, pull its data with `get_report_data` for the most
recent closed period. Then check whether department names appear in the row paths
— look for named path segments that correspond to functional areas (e.g. "Marketing",
"Finance", "Software Development", "R&D").

If no department dimension is present in the row data, tell the user clearly:
"This report doesn't appear to have department-level data — I can see account
totals but not which department each amount hit. For a department anomaly scan
you'll need a report with department as a dimension. Want to pick a different one?"

Do not proceed with the anomaly analysis on a report without department data.

### Building an ad-hoc report (last resort)

`build_report` is unreliable and is treated as a last resort. Only use it if every saved
income statement report has been ruled out (none have department data, or none exist).
State the fallback explicitly to the user.

Call `build_report` with:
- `statement_type`: `income_statement`
- `pivots`: `["Department", "account"]` (or `["Department", "Vendor"]` for
  vendor-level analysis)
- `comparison`: `month_over_month_6` gives you a 6-month window to spot patterns

**Validate the response.** If `build_report` returns no data rows, or rows where every
balance is zero/null, stop. Do not proceed with the anomaly analysis or generate any
reclass entries.

**On `build_report` failure, ask the user.** Re-show the saved IS reports from Step 3 and
ask which one to use instead, or ask for explicit instruction (different period, different
entity, manually-specified report ID, abort). Do not silently fall back or fabricate data.

### What to flag

Read `references/anomaly-rules.md` for the full rule set. In summary, flag any row
where a GL account appears in a department it doesn't logically belong to. The main
categories:

| GL Account Pattern | Expected Departments | Anomaly if found in |
|---|---|---|
| 80xxxx–81xxxx (Hardware Dev, Manufacturing, Lab, Tooling, Regulatory, NPI) | R&D departments | S&M, G&A, COGS |
| 70xxxx (Brand, PR, Creators, Performance Media, Wholesale Mktg) | Sales & Marketing | R&D, G&A |
| 54xxxx (Reliability Testing, COGS) | COGS / R&D | S&M, G&A |
| 650130 (Legal Fees) | Legal | Any non-Legal dept |
| 651100 (HR Expense) | Talent / HR | Any non-Talent dept |
| 670xxx (Lease, Rent, Utilities, Janitorial, CAM) | G&A (Finance or Talent) | R&D, S&M |

Also flag:

- **New large items**: $0 in prior month → >$10K in current month (suggests a new
  miscoding or structural change)
- **Extreme variance**: >500% change where both periods are non-zero
- **Round-number manual journals**: large round-dollar entries often indicate manual
  reclasses that may themselves be wrong

These rules are a starting point. Every company's chart of accounts is different.
Adapt based on what you learn from the workspace's actual GL structure — if you see
account names or codes that don't fit the patterns above, use judgment.

## Step 4: Drill into transaction lines

For each flagged row, use `query_transaction_lines` to pull the underlying entries.
This is where you confirm root causes. Look for:

- **Transaction type**: `Journal` entries (manual reclasses) vs. `VendBill` (vendor
  bills) vs. `CardChrg` (credit card charges from Ramp/Brex/etc.)
- **Memo/description**: often reveals intent — "R&D accessories purchase" coded to
  Marketing means the employee's card default department is wrong
- **Counterparty**: manufacturing vendors (e.g., Chinese contract manufacturers)
  appearing in non-R&D departments are almost always miscodings
- **Recurring journal entries**: look for JE memos like "Department Review Reclasses"
  or "Department mapping adjustments" — these are systematic reclasses that may
  themselves be sending costs to the wrong place
- **Stale transactions**: credit card charges with transaction dates months before
  the posting date indicate late-syncing expenses

Prioritize drilling into the largest-dollar anomalies first. Use `limit` on the
query to keep responses manageable (start with 50 lines).

## Step 5: Generate the NetSuite CSV reclass

For each confirmed anomaly, create a balanced journal entry that:

1. **Credits** the GL account in the **wrong** department (removes it)
2. **Debits** the same GL account in the **correct** department (adds it)

If the anomaly also involves a wrong GL account (e.g., a donation coded as HR
Expense), cross both the GL and the department in the same entry.

### CSV format

Use this column structure for NetSuite JE CSV import:

```
External ID,Tran Date,Subsidiary,Currency,Header Memo,Account,Debit,Credit,Department,Class,Location,Name,Line Memo
```

Rules:
- **External ID**: use pattern `RECLASS-YYYY-MM-NNN` (e.g., `RECLASS-2026-01-001`).
  Populate on the first line of each JE only; leave blank for subsequent lines.
- **Tran Date, Subsidiary, Currency, Header Memo**: same — first line only.
- **Tran Date**: use the last day of the period being corrected (e.g., `1/31/2026`).
- **Account**: use the GL account number (e.g., `701400`), not the name.
- **Debit/Credit**: format as `12345.67`. Leave the opposite column blank.
- **Department**: use the full department path as it appears in NetSuite
  (e.g., `Sales and Marketing : Consumer Marketing`).
- **Line Memo**: describe what's being reclassed and why. Reference the original
  JE number if the anomaly was caused by a specific journal entry.
- Flag any entries that need management confirmation with `[REVIEW W/ MGMT]` in
  the header memo (e.g., PR spend under the CEO may be intentional).

### Verification

After generating the CSV, verify programmatically that debits equal credits for
every journal entry. Print a summary showing each JE's external ID, debit total,
credit total, and balance status.

### Output

Save the CSV to the outputs folder. Present the user with:
1. A summary table of all JEs (JE number, account, amount, from → to)
2. The verification results
3. Notes on any entries flagged for management review
4. A link to the CSV file

## Performance

This skill runs long. Before drilling, fan out per anomaly, apply a materiality gate, default to a 6-month report window with tight drill windows, and checkpoint per anomaly. See `references/performance.md` for the full pattern. Use `scripts/aggregate_anomalies.py` to produce the flagged anomaly list instead of pivoting inline.

## Adapting to different companies

This skill was built from a workflow on a hardware/software company with departments
like R&D : Hardware, Sales and Marketing : Creative, G&A : Legal, etc. Other
companies will have different department structures. When scanning a new workspace:

- Start by reading the department names from the report data (they appear in the
  path structure, e.g., `path_s#1 > path#102` with department names in the summary
  rows)
- Map each department to its functional area (R&D, S&M, G&A, COGS) based on the name
- Adapt the anomaly rules accordingly — the principle is the same (manufacturing
  costs shouldn't be in marketing, marketing costs shouldn't be in R&D), but the
  specific department names and GL account ranges will vary
