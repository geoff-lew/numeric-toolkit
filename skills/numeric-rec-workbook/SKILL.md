---
name: numeric-rec-workbook
description: >
  Generates a Numeric Rec workbook (.xlsx) from live Numeric data for any GL account.
  Builds a clean leadsheet with one row per account and entity — date headers fill in
  automatically across the top, and GL balances are pulled from Numeric and populated in
  blue. Includes a rollforward tab pre-wired to the Numeric tab. Also supports dropping a
  Numeric tab into an existing workbook without touching any other sheets. Always asks for
  period, entity, and account before building unless already clear from context. Trigger
  whenever a user wants to build rec support, a leadsheet, a subledger file, or a rollforward
  workbook for any account — phrases like "make me the workbook for account 1200", "build rec
  support for Prepaid", "create the leadsheet for account 2505", "generate a workbook for
  account 1405", "add a Numeric Leadsheet to my workbook", or "I need support for this rec".
---

# GL Rec Workbook — Numeric Leadsheet Skill

Builds a Numeric Leadsheet `.xlsx` from live Numeric data. One template, simple output.

---

## Step 0 — Clarify before building

Before asking the user for anything, try to detect what you already have:

**If a spreadsheet was provided**, scan it first (first 20 rows of each sheet) for:
- A GL account code (4–6 digit number) → use as account
- A month/year value (e.g. "March 2025", "Mar-25", "3/31/2025") → use as period
- An entity code or name matching workspace context → use as entity

Then call `get_workspace_context` to get real entity codes and names.

Only ask for values that couldn't be detected. Use `AskUserQuestion` to collect anything still missing:

1. **Account** — GL code(s) (e.g. `1405`, `1210`)
2. **Entity** — show the user real entity codes + names from workspace context so they can pick
3. **Period** — month/year slug (e.g. `mar-2025`)

Confirm any auto-detected values with the user before proceeding: *"I found account 1405, March 2025, and entity US — does that look right?"*

Prior period balances are included automatically if the data exists in Numeric. No need to ask — attempt to pull them and fall back silently if unavailable.

If the user already specified account and workspace earlier in the conversation, you likely already have entity codes — skip refetching.

---

## Prerequisites

The recalc script is bundled at:

```
${CLAUDE_PLUGIN_ROOT}/skills/numeric-rec-workbook/scripts/recalc.py
```

Copy it to the working directory before use:

```bash
cp "${CLAUDE_PLUGIN_ROOT}/skills/numeric-rec-workbook/scripts/recalc.py" /tmp/recalc.py
```

The leadsheet template lives in this skill's `assets/` folder:

```
${CLAUDE_PLUGIN_ROOT}/skills/numeric-rec-workbook/assets/tmpl_leadsheet.xlsx
```

It has two sheets:

**Sheet 1 — Numeric** (the leadsheet Numeric reads — always first tab):
- Row 1: `Account | Entity | C1=start_date | D1=EOMONTH(C1,1) | ... | N1=EOMONTH(M1,1)`
- Row 2: account code | entity code | 3 prior period balances (blue, hardcoded) | current period formula `=Rollforward!C11`

**Sheet 2 — Rollforward** (the support/working tab):
- Row 1: dark blue banner
- Rows 3–5: Account / Entity / Period (yellow input cells B3, B4, C5)
- Row 7: Beginning Balance (prior period GL — blue font, B7)
- Row 8: Additions (zero by default, B8)
- Row 9: Reductions (zero by default, B9)
- Row 11: Ending Balance — formula `=B7+B8-B9` (C11)
- Row 12: GL Balance (Numeric) — hardcoded from Numeric API (blue font, C12)
- Row 13: Variance — formula `=C11-C12` (C13)

The Numeric tab's current period balance links to the Rollforward ending balance via
`=Rollforward!C11` — so changes in the Rollforward flow through automatically.

---

## Data Gathering

### Step 1 — Account lookup
`list_financial_accounts` → find by code. Capture `external_id`, `name`, `category`.

Normal balance: ASSET/EXPENSE = debit normal; LIABILITY/REVENUE/EQUITY = credit normal.

### Step 2 — Workspace context
`get_workspace_context` → get period IDs and entity codes/names.
Map period slug → period ID. If prior periods are included, also map the 3 prior month slugs → period IDs.
Compute the **last day** of the current month (and 3 prior months if included) using `calendar.monthrange`.
These are the column headers in the Numeric tab.

### Step 3 — GL balances (current + optional 3 prior periods)

Use `list_tasks` for the current period to find the rec task for this account.
The task list is TSV — parse headers from line 2, data from line 3 onward.
The `key_id` field encodes entity: `{gl_connection_id}/{entity_code}/{account_external_id}`.

Use a balance sheet report (`list_reports` → find statement_type balance_sheet,
then `get_report_data`) to get balances. Call it once per period needed:

```python
# Call get_report_data for current period and each of the 3 prior periods
# configuration_id = the urc_... ID from list_reports (reportConfig.id field)
# period_id = the per_... ID from workspace context

# Parse the TSV response — find the row matching the account external_id and entity
# Row key format: path#{entity_code} > ... > path#{entity_code}/{account_external_id}
# Extract the balance from the current-period column
```

Collect:
- `bal_current` — current period balance (F column, formula-linked via Rollforward) — always pulled

If prior periods are included, also collect:
- `bal_3_prior` — balance 3 months before current (C column in Numeric tab)
- `bal_2_prior` — balance 2 months before current (D column)
- `bal_1_prior` — balance 1 month before current (E column) → also used as Beginning Balance in Rollforward

If prior period data is unavailable (account not in report, period not open), set the missing values to `None` and continue — the workbook will be built with whatever is available.

If an account has no balance in a prior period (no row in the report), use `0`.

If you already have some balances from earlier in the conversation, reuse them to avoid
redundant API calls.

---

## Building the Workbook

### Step A — Copy template (never modify in-place)

```python
import shutil, os, openpyxl, datetime, calendar
from openpyxl.styles import Font

SKILL_DIR = os.path.join(os.environ.get("CLAUDE_PLUGIN_ROOT", "."), "skills", "numeric-rec-workbook")
shutil.copy(f"{SKILL_DIR}/assets/tmpl_leadsheet.xlsx", "/tmp/output.xlsx")
os.chmod("/tmp/output.xlsx", 0o644)
wb = openpyxl.load_workbook("/tmp/output.xlsx")
ws_num = wb["Numeric"]
ws_rf = wb["Rollforward"]
AMT = '#,##0.00;(#,##0.00);"-"'
BLUE = Font(name="Arial", color="0000FF", size=10)
```

### Step B — Set the start date in C1 (Numeric tab)

If prior periods are included: set `C1` to the **last day of the month 3 months before the current period**.
If prior periods are skipped: set `C1` to the **last day of the current period month** — current period balance will land in C2 instead of F2, and columns D onward will be blank.

The EOMONTH formulas in D1–N1 already exist in the template and will auto-cascade.

Example (with priors): current period = Mar 2025 → set `C1 = datetime.date(2024, 12, 31)`
Result: C=12/31/24, D=1/31/25, E=2/28/25, F=3/31/25

Example (without priors): current period = Mar 2025 → set `C1 = datetime.date(2025, 3, 31)`
Result: C=3/31/25, D=4/30/25, …

```python
# start = 3 months before current period
start_year, start_month = ...  # compute by subtracting 3 months
ws_num["C1"] = datetime.date(start_year, start_month, calendar.monthrange(start_year, start_month)[1])
ws_num["C1"].number_format = "M/D/YYYY"
```

### Step C — Populate the Numeric tab (all 4 balance columns)

The current period is always column F (offset 3 from C, i.e., the 4th date column).

```python
ws_num["A2"] = int(acct_code)
ws_num["B2"] = int(entity_code)

# Prior 3 months — hardcoded, blue font (only if prior periods included)
if bal_3_prior is not None:
    for col_offset, bal in enumerate([bal_3_prior, bal_2_prior, bal_1_prior]):
        cell = ws_num.cell(row=2, column=3 + col_offset)  # C2, D2, E2
        cell.value = bal
        cell.font = BLUE
        cell.number_format = AMT
    current_col = "F2"
else:
    current_col = "C2"  # No priors — current period starts at C

# Current period — formula linking to Rollforward ending balance
ws_num[current_col] = "=Rollforward!C11"
ws_num[current_col].number_format = AMT

# Clear future period columns (G2 onward)
for col in range(7, ws_num.max_column + 1):
    ws_num.cell(row=2, column=col, value="")
```

### Step D — Populate the Rollforward tab

```python
ws_rf["B3"] = int(acct_code)
ws_rf["B4"] = int(entity_code)
ws_rf["C5"] = period_label            # e.g. "March 2025"

# Beginning balance = bal_1_prior if available, else 0
ws_rf["B7"] = bal_1_prior if bal_1_prior is not None else 0
ws_rf["B7"].font = BLUE
ws_rf["B7"].number_format = AMT

# Additions / Reductions = 0 by default; preparer fills in
ws_rf["B8"] = 0
ws_rf["B8"].number_format = AMT
ws_rf["B9"] = 0
ws_rf["B9"].number_format = AMT

# GL Balance (Numeric) = current period GL, blue font
ws_rf["C12"] = bal_current
ws_rf["C12"].font = BLUE
ws_rf["C12"].number_format = AMT

# C11 (=B7+B8-B9) and C13 (=C11-C12) are already formulas in the template
ws_rf["C11"].number_format = AMT
ws_rf["C13"].number_format = AMT
```

### Step E — Validate and save

```python
wb.save("/tmp/output.xlsx")
# python /tmp/recalc.py /tmp/output.xlsx 30
# Must return {"status": "success", "total_errors": 0}
```

Save to the outputs folder:

```bash
cp /tmp/output.xlsx "<outputs_folder>/<filename>.xlsx"
```

---

## Mode 2 — Add Numeric Tab to Existing Workbook

When the user provides an existing `.xlsx`, open it and intelligently detect what's already there before building the Numeric tab.

### Step M1 — Inventory the workbook

```python
wb = openpyxl.load_workbook("/tmp/existing.xlsx")
sheets = wb.sheetnames  # e.g. ["Rollforward", "Support", "JE Detail"]
```

Print the sheet names to the conversation so the user can see what was found.

### Step M2 — Detect account and period

Scan the existing sheets for recognisable account and period values:
- Look for cells containing a GL account code pattern (4–6 digit number) in the first 20 rows of each sheet
- Look for cells containing a month/year pattern (e.g. "March 2025", "Mar-25", "3/31/2025") in the first 20 rows
- If found, use these as the account and period — confirm with the user before proceeding
- If not found, ask the user to provide account and period explicitly

### Step M3 — Find the ending balance cell

Scan existing sheets for a cell that looks like an ending balance to link to:
- Search for labels like "Ending Balance", "End Balance", "Ending", "Total", "Balance" in column A or B within the first 50 rows of each sheet
- Prefer sheets named "Rollforward", "Support", "Workpaper", "Rec", or similar
- Once identified, capture the sheet name and cell address (e.g. `Support!C11`)
- If a clear candidate is found, confirm with the user: *"I found what looks like an ending balance at [Sheet]![Cell]. Should I link the Numeric tab to this cell?"*
- If nothing is found, hardcode `bal_current` directly instead of using a formula

### Step M4 — Build and insert the Numeric tab

1. Insert a new sheet named `"Numeric"` at position 0 — **do not modify any existing sheets**
2. Follow Steps B–C above to populate it, with one change:
   - Replace `=Rollforward!C11` with `=[DetectedSheet]![DetectedCell]` if a link was found
   - Otherwise hardcode `bal_current` in blue font
3. Save as `{original_filename}_with_numeric_tab.xlsx`

---

## Output Filename

```
Numeric_Leadsheet_{AccountCode}_{WorkspaceName}_{MonthAbbr}{Year}.xlsx
```
Examples: `Numeric_Leadsheet_1405_Supernova_Mar2025.xlsx`

---

## Post-Delivery Note

The workbook must be manually uploaded in Numeric's UI to the subledger field of the
reconciliation task. The **Numeric** tab is what Numeric reads for the balance tie-out.
