---
name: report-txn-detail
user-invocable: true
description: >
  Pull any Numeric report (IS, BS, or saved config) and produce an Excel workbook with two tabs:
  the full report and a flat table of every GL transaction line. Trigger for: "report with
  transaction detail", "GL detail behind the report", "report with drill-down", "IS with
  transactions", "BS with line items", "report with supporting detail", "give me the report and
  the journal entries", "what's in each account", "show me what makes up each line on the P&L",
  "detail behind the numbers", "report with backup", "BS with GL detail", "pull the financials
  and show me the lines", or any request combining a Numeric report with underlying transaction
  data. Also trigger for mentions of Numeric plus transaction lines, journal entries, or GL detail.
---

# Report with Transaction Detail

Pull any Numeric report and produce an Excel workbook with two tabs: the report itself and a flat table of every GL transaction line behind each account.

## Why This Exists

Controllers and accountants frequently need to see both the high-level report and the transactions behind each number — for review, audit support, or just understanding what drove a balance. This skill automates the manual process of clicking into each account row in Numeric and copying out the detail.

## Workflow

### Step 1: Identify Workspace and Period

1. Call `list_workspaces` to show available workspaces
2. If the user hasn't specified, ask which workspace
3. Call `set_workspace` with the chosen workspace
4. Call `get_workspace_context` to get:
   - Available periods (and their `period_id` values)
   - Entities and their `gl_connection_id` values
5. Confirm the target period with the user (default to most recent closed period if not specified)

### Step 2: Pull the Report

This skill works with any Numeric report — income statement, balance sheet, or any saved custom report configuration.

GL data must be pulled through this ordering. Do not skip steps. `build_report` is unreliable and is treated as a last resort.

1. **Call `list_reports` first.** Inspect saved configurations for matches by `statement_type`, comparison, and name.
2. **Use `get_report_data(configuration_id, period_id)` for any matching saved report.** If multiple plausibly match, show the user the top 2–3 and let them pick — do not silently pick. This returns TSV.
3. **Only fall back to `build_report` when no saved config can serve the need.** State the fallback explicitly to the user. Determine `statement_type` (`income_statement` / `balance_sheet`), pick `comparison` from the table below (default `single_month` unless the user specified), and call `build_report(statement_type, gl_connection_id, as_of_year, as_of_month, comparison)`.
4. **Validate the `build_report` response.** If it returns no data rows, or rows where every balance is zero/null, stop. Do not produce a partial or empty workbook.
5. **On `build_report` failure, ask the user.** Show them the saved configs from step 1 and ask which one to use instead, or ask for explicit instruction (different period, different entity, manually-specified report ID, abort).

| User says | comparison value |
|---|---|
| "this month", "March", "single month" | `single_month` |
| "year to date", "YTD" | `year_to_date` |
| "last 3 months", "MoM", "trailing 3" | `month_over_month_3` |
| "last 6 months", "half year" | `month_over_month_6` |
| "last 12 months", "full year", "MoM 12" | `month_over_month_12` |
| "quarter to date", "QTD" | `quarter_to_date` |

### Step 3: Parse the Report Response

The report comes back as TSV. Parse it to extract:

- **Every row as-is** for the report tab (preserve the full report structure including group headers, subtotals, computed rows, margins — everything)
- **Row keys**: each row has a `key` object with `id` and `type` fields — needed for transaction queries
- **Row types**: identify which rows are drillable accounts (`financial_account`, `external_account_id`, `path`) vs. summary/group rows (`computed_row`, `custom_group`). Only drillable rows get transaction line queries.
- **Group membership**: track which report section/group each drillable account belongs to (e.g., "Revenue", "Cost of Revenue", "Operating Expenses", "Assets", "Liabilities"). This becomes the "Report Group" column on the Transaction Lines tab.

### Step 4: Determine the Date Window

Transaction line queries need `window_start` and `window_end`. Derive from the report period:

- **Income statement / single month**: first day → last day of the as-of month
- **Income statement / YTD**: Jan 1 → last day of the as-of month
- **Income statement / QTD**: first day of the quarter → last day of the as-of month
- **Income statement / MoM (3, 6, 12)**: first day of the earliest comparison month → last day of the as-of month
- **Balance sheet**: first day → last day of the as-of month (shows period activity)

Use Python's `calendar.monthrange()` for end-of-month dates.

### Step 5: Query Transaction Lines for Each Account

For every drillable row from Step 3:
1. Call `query_transaction_lines(report_id, key, window_start, window_end)`
   - `report_id`: the saved report's `reportConfig.id` from `list_reports` (preferred). Use the `build_report` response's report ID only when the saved-report path was not viable.
   - `key`: the row's key object `{id, type}`
   - `window_start` / `window_end`: date objects `{year, month, day}`
2. The response is TSV with transaction-level columns (date, posting date, transaction type, name, memo, amount, counterparty, department, organization, currency, URL, etc.)
3. For each returned line, tag it with the account name and the report group from Step 3
4. Append all lines to a single flat collection

**Progress updates:** Give the user updates every 10 accounts (e.g., "Pulled detail for 20 of 45 accounts...").

**Empty results:** Some accounts may have zero transactions in the window. That's normal — just skip them (no placeholder rows needed).

### Step 6: Build the Excel Workbook

Read the xlsx skill for Excel best practices (formatting, recalc).

Create an `.xlsx` workbook with two sheets:

#### Sheet 1: Report tab

Name this sheet to match the report type (e.g., "MoM Income Statement", "Balance Sheet", "YTD P&L" — whatever describes the report).

Reproduce the full report exactly as returned from Numeric:
- **Column A**: Name (account number + name, or group/subtotal label — exactly as returned)
- **Remaining columns**: one per period/comparison column, plus Variance ($) and Variance (%) if present
- Include ALL rows — accounts, group subtotals, computed rows, margins. Don't filter anything out.
- Number format: `#,##0.00;(#,##0.00);"-"` for monetary values
- Percentage columns: `0.00%` or display the raw decimal as returned

This tab is a faithful reproduction of the Numeric report. Don't restructure it, don't add metadata headers, don't insert SUM formulas — just write the data as-is.

#### Sheet 2: "Transaction Lines"

A single flat table with every transaction line from all accounts. One header row, then one row per transaction. Columns:

| Column | Description |
|---|---|
| Report Group | The report section this account falls under (e.g., "Revenue", "Cost of Revenue", "Operating Expenses", "Other Expense / Income") |
| Account Name | Full account label as shown in the report (e.g., "40100 - Flat Usage") |
| Transaction Date | The transaction date |
| Posting Date | The posting/effective date |
| Transaction Type | Type of transaction (Journal, Invoice, Bill, etc.) |
| Transaction Name | Document name/number (e.g., "Journal #REV7n_0326_CT") |
| Memo | Transaction memo/description |
| Net Amount | The net amount (single column, not split into debit/credit) |
| Counterparty | Vendor, customer, or entity name |
| Department | Department if present |
| Organization | The entity/subsidiary |
| Currency | Transaction currency |
| Transaction URL | Link back to the transaction in the ERP (if available) |

Key formatting details:
- **Freeze the header row** (row 1)
- **Auto-filter** on the header row so users can filter/sort by Report Group, Account, Counterparty, Department, etc.
- Column widths: Account Name ~35, Memo ~50, Transaction Name ~35, Net Amount ~15, others ~15
- Net Amount format: `#,##0.00;(#,##0.00);"-"`
- Transaction URL: if present, make it a clickable hyperlink

The data should be ordered the same way the report is ordered — Revenue accounts first, then COGS, then OpEx, etc. (for IS). Within each account, order by transaction date.

This flat structure is intentional — it lets users pivot, filter, and sort freely in Excel without having to work around grouped layouts.

### Step 7: Save and Deliver

1. Save the workbook
2. Run the xlsx recalc script if any formulas were used:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/skills/numeric-rec-workbook/scripts/recalc.py" <output_file>
   ```
3. Copy to the output directory and provide the download link

**File naming**: `{Entity}_{ReportName}_{YYYY-MM}.xlsx`
Examples:
- `Acme_Corp_MoM_IS_Mar2026.xlsx`
- `Acme_Corp_Balance_Sheet_Dec2025.xlsx`
- `Acme_Corp_YTD_Income_Statement_Jun2026.xlsx`

## Performance

This skill runs long. Before drilling, fan out per account, apply a materiality gate, default to a single-month window, and checkpoint each subagent's output. See `references/performance.md` for the full pattern and parameters. Use `scripts/parse_report.py` (in this skill's `scripts/` folder) to parse the report TSV instead of doing it inline.

## Edge Cases

- **Report has no data rows**: Tell the user the report is empty for that period. Don't create a file.
- **Very high transaction volume (10K+ lines)**: This is normal for large companies. Include all lines — Excel handles it fine. Warn the user about file size if it exceeds ~50K rows.
- **Multiple entities**: If the user asks for all entities, create one workbook per entity. Name files distinctly.
- **Comparison reports (MoM, YTD)**: The report tab includes all comparison columns. The Transaction Lines tab queries transactions for the full comparison window (Step 4 handles this). If the window is very wide (12 months), warn the user it may take a while and produce a large file.
- **Saved report with custom groupings**: Some saved reports use custom account groupings or pivot by department/class. The Report Group column should reflect whatever grouping structure the saved report uses.
- **report_id source**: Default to `reportConfig.id` from `list_reports`. Only use the `build_report` response's report ID if the saved-report path wasn't viable and `build_report` actually returned populated rows.
- **`build_report` returned empty / all-zero rows**: Halt. Do not produce a workbook. Show the user the saved configs from `list_reports` and ask which one to use instead, or ask for further instruction.
- **Balance sheet reports**: The Report Group column maps to sections like "Assets", "Liabilities", "Equity". The transaction window covers the as-of month's activity.
- **Accounts with no transactions**: Skip them on the Transaction Lines tab — no empty placeholder rows.
