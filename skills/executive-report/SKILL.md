---
name: executive-report
description: >
  Generates a board-ready or CFO-ready financial statement from Numeric data. Collapses child
  account detail into executive summary groups, rolls up flux commentary into one-line narratives
  per group, applies professional financial statement formatting, and outputs as a formatted Excel
  workbook or PDF. Trigger when the user asks for "executive report", "board report", "CFO report",
  "board package", "board deck financials", "executive summary financials", "clean financial
  statement", "collapse the report", "summarize the financials for the board", "roll up the P&L",
  "high-level income statement", "presentation-ready financials", "investor report",
  "management report", or any request for a polished, condensed financial output rather than
  a detailed close management view.
---

# Executive Report

Generate a board-ready or CFO-ready financial statement from Numeric. Strip all close management
metadata, collapse child account detail into executive summary groups, roll up flux commentary
into concise narratives, and output a presentation-quality Excel or PDF artifact.

This skill produces a **presentation artifact** — not a data export and not a close management
view. The output should be indistinguishable from something a CFO would hand to the board.

---

## Step 0: Clarify before building

Ask the user (or infer from context):

1. **Workspace** — which Numeric workspace?
2. **Period** — which month/quarter? (single period or comparison?)
3. **Entity scope** — single entity, or multi-entity (consolidated or per-entity sheets)?
4. **Output format** — Excel (.xlsx) or PDF?
5. **Comparison** — prior month, prior quarter, prior year, budget vs. actual, or none?

If the user says "just make it" without specifying, default to: single entity, current period
vs. prior month, Excel output. Confirm the defaults before proceeding.

---

## Step 1: Pull source data

```
get_workspace_context       → entity list, period IDs, gl_connection_id
list_reports                → find IS and BS report configs
get_report_data             → IS data for target period (+ comparison period if requested)
get_report_data             → BS data for target period
list_financial_accounts     → chart of accounts for group mapping
list_tasks(period_id, task_type="flux")  → flux tasks for commentary rollup
```

For multi-period comparisons, pull each period's report data separately.

For multi-entity (consolidated): pull `build_report` per entity with `pivots: ["account", "org"]`
then aggregate. Flag to the user if intercompany elimination is needed — do not silently net
intercompany unless the user confirms it.

---

## Step 2: Collapse to executive groups

Strip all child account detail. Collapse the full chart of accounts into these standard
executive statement groups:

### Income Statement groups

| Group | What it includes |
|---|---|
| Revenue | All revenue accounts — subscription, license, services, other revenue |
| Cost of Revenue | All COGS accounts — hosting, support, direct labor, merchant fees |
| **Gross Profit** | Revenue − Cost of Revenue *(computed)* |
| R&D | All R&D / engineering / product development expense |
| Sales & Marketing | All S&M / marketing / customer acquisition expense |
| General & Administrative | All G&A / corporate / finance / legal / HR expense |
| **Total Operating Expenses** | Sum of R&D + S&M + G&A *(computed)* |
| **Operating Income (Loss)** | Gross Profit − Total OpEx *(computed)* |
| Other Income / (Expense) | Interest income, interest expense, FX gains/losses, other non-operating |
| Income Tax | Tax provision |
| **Net Income (Loss)** | Operating Income + Other Income − Tax *(computed)* |

### Balance Sheet groups (if requested)

| Group | What it includes |
|---|---|
| Cash & Equivalents | All cash and short-term investment accounts |
| Accounts Receivable | Trade receivables and unbilled revenue |
| Other Current Assets | Prepaid, inventory, deposits, other current |
| **Total Current Assets** | *(computed)* |
| Fixed Assets, net | PP&E net of accumulated depreciation |
| Intangibles & Other | Capitalized software, goodwill, other long-term assets |
| **Total Assets** | *(computed)* |
| Accounts Payable | Trade payables |
| Accrued Liabilities | Accrued expenses, accrued compensation |
| Deferred Revenue | Current deferred revenue |
| Other Current Liabilities | Other short-term obligations |
| **Total Current Liabilities** | *(computed)* |
| Long-term Debt | Term loans, notes payable, non-current borrowings |
| Other Long-term Liabilities | Non-current deferred revenue, lease obligations, other |
| **Total Liabilities** | *(computed)* |
| Total Equity | Paid-in capital + retained earnings + accumulated OCI |
| **Total Liabilities & Equity** | *(computed)* |

### Group mapping logic

Use `list_financial_accounts` to map each account to its executive group:

1. Use the account's `category` / `type` field as the primary signal (REVENUE, COGS, EXPENSE, ASSET, LIABILITY, EQUITY)
2. Use the account name and parent path to distinguish OpEx sub-groups (R&D vs. S&M vs. G&A)
3. If an account doesn't clearly map, assign it to the nearest logical group and note it in
   the "Account Mapping Notes" section at the bottom of the output
4. Never drop an account silently — every dollar must land somewhere

Sum all accounts within each group to produce the group-level balance.

---

## Step 3: Roll up flux commentary

For each IS group that has a material variance (>5% or >$10K vs. comparison period):

1. Call `list_tasks` with `task_type="flux"` and the target `period_id`
2. For each flux task that maps to this group's accounts, call `get_task_comments` to pull
   the preparer's explanation
3. Synthesize child-level explanations into a single concise narrative (1–2 sentences max):
   - Lead with direction and magnitude at the group level: "R&D up 12%"
   - Attribute to 2–3 specific drivers: "driven by 3 new hires in Feb ($45K) and
     increased AWS usage ($18K)"
   - If no flux commentary exists for a group, omit the narrative rather than fabricating one

**Good narrative**: "Sales & Marketing up 23% ($341K) driven by Q1 campaign spend ($180K)
and 2 new SDR hires ($95K salary + benefits)."

**Bad narrative**: "Sales & Marketing expenses increased compared to the prior period."

Place the narrative as a note row directly below the group line in the output.

---

## Step 4: Detect currency and brand

### Currency

For each entity, detect the reporting currency:
1. Check `organization_currency` on GL transaction lines via `query_transaction_lines` (sample 1 line)
2. Fall back to `currency_code` on accounts from `list_financial_accounts`
3. Default to USD ($) if undetectable — note the assumption to the user

Apply the correct symbol: USD = $, EUR = €, GBP = £, CAD = C$, AUD = A$, etc.

### Brand styling

Use Numeric's brand palette throughout. This report is a Numeric-generated artifact and should look like one.

| Element | Color | Notes |
|---|---|---|
| Header bar background | `#1F0045` | Deep navy-purple — full-width title row |
| Header text | `#FFFFFF` | White bold, 13pt |
| Section header rows (Revenue, COGS, R&D…) | `#1F0045` | White bold text |
| Subtotal rows (Gross Profit, Operating Income…) | `#EEEEEF` | Lavender-gray fill, `#1F0045` bold text |
| Net Income row | `#1F0045` | White bold text, double underline |
| Metric/ratio rows (Gross Margin %, EBITDA…) | `#F0EBFF` | Light violet fill, `#7036FF` italic text |
| Commentary narrative rows | `#F7F7FB` | Very light lavender, `#4D4D5B` italic 9pt |
| Positive variance | `#12B76A` | Numeric green |
| Negative / unfavorable variance | `#E53935` | Numeric red |
| Accent / progress fills | `#7036FF` | Numeric violet |
| Page background (PDF) | `#F7F7FB` | Light lavender-white |
| Body text | `#1F0045` | Primary dark navy |
| Secondary / muted text | `#778CA2` | Used for column headers, labels |

Font: Arial throughout. No other fonts.

---

## Step 5: Build the output

### Financial statement formatting rules

Apply these rules consistently across both IS and BS output:

**Hierarchy and indentation:**
- Group headers (Revenue, Cost of Revenue, R&D, etc.): bold, no indent, left-aligned
- Computed subtotals (Gross Profit, Operating Income, Net Income): bold, no indent
- Commentary narrative rows: italic, gray font (`#666666`), indented 1 level, 9pt

**Borders:**
- Single underline above subtotal rows (Gross Profit, Total OpEx, Operating Income)
- Double underline above and below Net Income (Loss)
- No borders on regular data rows

**Number formatting:**
- All monetary values: currency symbol + scale shorthand
  - ≥ $1M: display as `$X.XM` (e.g., `$66.0M`, `$(3.2M)`)
  - ≥ $1K: display as `$X.XK` (e.g., `$341.3K`)
  - < $1K: display as `$XXX`
- Negative values: parentheses, never minus sign — `(3,241)` not `-3,241`
- Percentage columns (variance %): `0.0%` format, red font if unfavorable
- Variance $ column: same scale shorthand, red font if unfavorable
- Zero balances: display as `—` (em dash), not `$0` or `$0.0M`

**Column layout (IS):**
```
| Account Group | [Period] | [Comparison Period] | Variance $ | Variance % | Commentary |
```

**Column layout (BS):**
```
| Account Group | [Period] | [Prior Period] | Change $ | Change % |
```

**Gross Margin line:**
Add a Gross Margin % row directly below Gross Profit:
`Gross Margin: XX.X%` — displayed inline, italic, indented

**EBITDA block:**
After Net Income, add a reconciliation block:
- Operating Income (Loss)
- + Depreciation & Amortization
- = **EBITDA**
- EBITDA Margin: XX.X%

### Multi-entity handling

**Consolidated view:**
- Sum all entities into a single column
- Add an "Entities included" note in the header
- If the user flags intercompany balances, add an "Intercompany Eliminations" row between
  entity subtotals and the consolidated total — but only if the user confirms the IC amounts

**Per-entity view:**
- One sheet per entity, named by entity name (not ID)
- Add a "Summary" sheet with all entities side by side for comparison

### Excel implementation (openpyxl)

```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

# Numeric palette
NAVY       = "1F0045"
VIOLET     = "7036FF"
LAVENDER   = "EEEEEF"
LT_VIOLET  = "F0EBFF"
LT_BG      = "F7F7FB"
GREEN      = "12B76A"
RED        = "E53935"
MUTED      = "778CA2"
SECONDARY  = "4D4D5B"

HEADER_FILL    = PatternFill("solid", fgColor=NAVY)
SECTION_FILL   = PatternFill("solid", fgColor=NAVY)
SUBTOTAL_FILL  = PatternFill("solid", fgColor="EEEEEF")
NETINC_FILL    = PatternFill("solid", fgColor=NAVY)
METRIC_FILL    = PatternFill("solid", fgColor="F0EBFF")
COMMENT_FILL   = PatternFill("solid", fgColor="F7F7FB")

HEADER_FONT    = Font(name="Arial", bold=True, color="FFFFFF", size=13)
SECTION_FONT   = Font(name="Arial", bold=True, color="FFFFFF", size=10)
SUBTOTAL_FONT  = Font(name="Arial", bold=True, color=NAVY, size=10)
NETINC_FONT    = Font(name="Arial", bold=True, color="FFFFFF", size=10)
METRIC_FONT    = Font(name="Arial", italic=True, color=VIOLET, size=10)
COMMENT_FONT   = Font(name="Arial", italic=True, color=SECONDARY, size=9)
DATA_FONT      = Font(name="Arial", color=NAVY, size=10)
LABEL_FONT     = Font(name="Arial", color=MUTED, size=9)

POS_VAR_FONT   = Font(name="Arial", color=GREEN, size=10)
NEG_VAR_FONT   = Font(name="Arial", color=RED, size=10)
```

- **Header bar**: rows 1–2 merged across all columns. Row 1 = Numeric wordmark + report title. Row 2 = entity name, period, generated date. `HEADER_FILL` background, `HEADER_FONT` text.
- **Column widths**: A = 44 (labels), data columns = 16, variance % = 10, commentary = 52
- **Row heights**: header rows = 28, section rows = 18, commentary rows = 26 (wrap_text=True)
- **Freeze panes**: B3
- **No gridlines**: `ws.sheet_view.showGridLines = False`
- **Tab color**: `1F0045`
- **Account Mapping Notes** at the bottom: `LABEL_FONT`, 9pt, `LT_BG` fill

### PDF output

If the user requests PDF:
1. Build the Excel workbook first (Step 5 above)
2. Convert to PDF using LibreOffice headless:
   ```bash
   libreoffice --headless --convert-to pdf --outdir /tmp/ /tmp/output.xlsx
   ```
3. Verify the PDF was created and is non-empty
4. Deliver the PDF; optionally also offer the Excel source

---

## Step 6: Deliver

Save to the outputs folder:
- Excel: `{WorkspaceName}_Executive_Report_{Period}.xlsx`
- PDF: `{WorkspaceName}_Executive_Report_{Period}.pdf`

Provide a brief inline summary alongside the file link:
- Revenue, Gross Margin %, Operating Income, Net Income for the period
- Top 1–2 variance drivers if flux commentary was available
- Note any accounts that couldn't be mapped or any assumptions made

Keep the summary to 3–5 lines. The document is the deliverable.

---

## Edge cases

- **No flux commentary available**: skip the narrative rows entirely — don't generate
  fabricated commentary. Note to the user that flux explanations weren't found.
- **Accounts that span multiple groups**: assign to the primary group based on account name.
  Note the assignment in Account Mapping Notes.
- **Prior period has no data**: show the current period column only. Mark comparison columns
  as "N/A — no prior period data."
- **Negative Gross Profit**: flag explicitly with a note: "Gross margin is negative this period."
- **PDF conversion failure**: deliver the Excel and note that PDF conversion failed. Suggest
  the user open and print-to-PDF manually.
- **Multi-currency entities in a consolidated view**: do not silently mix currencies. Ask the
  user which currency to consolidate into and what FX rate to apply (spot, average, or
  user-provided).
