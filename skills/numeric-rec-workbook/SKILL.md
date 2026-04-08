---
name: numeric-rec-workbook
description: >
  Generates a Numeric Rec workbook (.xlsx) from live Numeric data for any GL account.
  Uses a single clean leadsheet template — one row per account × entity, EOMONTH date formulas
  auto-cascade, all four period balances populated from Numeric rec data (blue font). Always asks
  the user for period, entity, and account before building (unless all three are already clear from
  context). Also supports adding a Numeric tab to an existing workbook without modifying other
  sheets. Trigger whenever a user wants to build rec support, a leadsheet, a subledger file, or a
  rollforward workbook for any account — phrases like "make me the workbook for account 1200",
  "build rec support for Prepaid", "create the leadsheet for account 2505", "generate a workbook
  for account 1405", "add a Numeric Leadsheet to my workbook", or "I need support for this rec".
---

# GL Rec Workbook — Numeric Leadsheet Skill

Builds a Numeric Leadsheet `.xlsx` from live Numeric data. One template, simple output.

---

## Step 0 — Clarify before building

Before writing any code, call `get_workspace_context` to get real entity codes and names,
then use `AskUserQuestion` to collect anything still missing:

1. **Account** — GL code(s) (e.g. `1405`, `1210`)
2. **Entity** — show the user real entity codes + names from workspace context so they can pick
3. **Period** — month/year slug (e.g. `mar-2025`)

If the user already specified account and workspace earlier in the conversation, you likely already
have entity codes — skip refetching.

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
Map period slug → period ID. Also map the 3 prior month slugs → period IDs.
Compute the **last day** of the current month and 3 prior months using `calendar.monthrange`.
These are the column headers in the Numeric tab.

### Step 3 — GL balances (current + 3 prior periods)

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
- `bal_3_prior` — balance 3 months before current (C column in Numeric tab)
- `bal_2_prior` — balance 2 months before current (D column)
- `bal_1_prior` — balance 1 month before current (E column) → also used as Beginning Balance in Rollforward
- `bal_current` — current period balance (F column, formula-linked via Rollforward)

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

Set `C1` to the **last day of the month 3 months before the current period** as a `datetime.date`.
The EOMONTH formulas in D1–N1 already exist in the template and will auto-cascade.

Example: current period = Mar 2025 → set `C1 = datetime.date(2024, 12, 31)`
Result: C=12/31/24, D=1/31/25, E=2/28/25, F=3/31/25, G=4/30/25, …

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

# Prior 3 months — hardcoded, blue font
for col_offset, bal in enumerate([bal_3_prior, bal_2_prior, bal_1_prior]):
    cell = ws_num.cell(row=2, column=3 + col_offset)  # C2, D2, E2
    cell.value = bal
    cell.font = BLUE
    cell.number_format = AMT

# Current period — formula linking to Rollforward ending balance
ws_num["F2"] = "=Rollforward!C11"
ws_num["F2"].number_format = AMT

# Clear future period columns (G2 onward)
for col in range(7, ws_num.max_column + 1):
    ws_num.cell(row=2, column=col, value="")
```

### Step D — Populate the Rollforward tab

```python
ws_rf["B3"] = int(acct_code)
ws_rf["B4"] = int(entity_code)
ws_rf["C5"] = period_label            # e.g. "March 2025"

# Beginning balance = bal_1_prior (most recent prior period GL), blue font
ws_rf["B7"] = bal_1_prior
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

When the user provides an existing `.xlsx` and wants a Numeric leadsheet tab added:

1. Open with `openpyxl` — inventory existing sheets, **do not touch them**
2. Insert a new sheet named `"Numeric"` at position 0
3. Follow Steps B–D above to populate it
4. Save as `{original_filename}_with_leadsheet.xlsx`

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
