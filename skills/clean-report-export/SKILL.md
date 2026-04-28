---
name: clean-report-export
user-invocable: true
description: >
  Generate a clean, analysis-ready financial statement export from Numeric with zero manual cleanup.
  Strips summary rows, fixes formatting, and outputs CSV/TSV ready for Excel, pandas, or BI tools.
  Use this skill whenever a user asks to "export a report", "download report data", "get me a clean CSV",
  "pull the income statement into Excel", "export the balance sheet", "give me the raw data from Numeric",
  "I need a clean version of this report", "export for analysis", "get me report data without the junk rows",
  "pull multiple reports", or any request that involves getting financial report data out of Numeric in a
  clean, machine-readable format. Also trigger when the user mentions TSV, CSV, or data export in the
  context of financial statements or Numeric reports.
---

# Clean Report Export

Generate analysis-ready financial data from Numeric reports. Every row is a pure data record — no merged cells, no summary artifacts, no formatting noise.

## Routing: Saved Report vs. Ad-Hoc Build

Ask the user (or infer from context) whether they want a saved report or an ad-hoc build:

**Saved report path:**
1. Call `list_reports` to get all saved configurations
2. Match the user's intent to the closest config by name and statement type (e.g., "income statement" → look for IS configs, "balance sheet" → BS configs)
3. If ambiguous, show the user the top 2-3 matches and let them pick
4. Call `get_report_data` with the matched `configuration_id` and the target `period_id`

**Ad-hoc build path:**
1. Call `get_workspace_context` to get entity list and `gl_connection_id` values
2. If multiple entities, ask which one (or loop through all if bulk requested)
3. Call `build_report` with the right `statement_type`, `gl_connection_id`, `as_of_year`, `as_of_month`

## Selecting the Right Comparison Type

Match the user's request to the `comparison` parameter on `build_report`:

| User says | comparison value |
|---|---|
| "this month", "March", "snapshot" | `single_month` |
| "year to date", "YTD" | `year_to_date` |
| "last 3 months", "trending", "MoM" | `month_over_month_3` |
| "last 6 months", "half year trend" | `month_over_month_6` |
| "last 12 months", "full year trend" | `month_over_month_12` |
| "quarter to date", "QTD" | `quarter_to_date` |

If the user doesn't specify, default to `single_month` and mention what you chose.

## Cleaning the Data

The raw TSV from Numeric contains summary/aggregation rows and group headers mixed in with data rows. Clean them out:

1. **Identify row types** — look at the `key_type` or row structure in the response. Summary rows, group headers, and computed subtotals typically have different key types (e.g., `computed_row`, `custom_group`) vs. leaf account rows (`financial_account`, `external_account_id`, `path`)
2. **Strip non-data rows** — remove rows that are subtotals, group headers, section separators, or blank spacer rows. Keep only rows that represent actual GL accounts with balances
3. **Preserve hierarchy info** — if the user wants hierarchy context, add a `group` or `parent` column derived from the section the account falls under, rather than keeping the raw group header rows

## Formatting

Apply these formatting rules to the cleaned data:

- **Monetary values**: default to raw numbers. If user requests scaling, apply `$K` (divide by 1,000) or `$M` (divide by 1,000,000)
- **Currency symbol**: read `organization_currency` from GL lines via `query_transaction_lines` or infer from `get_workspace_context` entity metadata. Apply correct symbol (USD $, EUR €, GBP £, etc.)
- **Percentages**: format ratio/percentage rows with `%` suffix and user-specified decimal precision (default 1)
- **Decimals**: monetary values default to 2 decimal places unless user specifies otherwise
- **Negative values**: default to minus sign. If user requests accounting format, use parentheses

## Output

Write the final output as a file:
- Default format: TSV (tab-separated, `.tsv`)
- If user requests CSV: comma-separated, `.csv`
- Include a header row with clean column names
- File name: `{entity}_{statement_type}_{period}_{comparison}.tsv` (e.g., `Acme_IS_2026-03_MoM3.tsv`)

## Bulk Mode

If the user requests multiple reports (e.g., "export all my income statements" or "pull IS and BS for all entities"):

1. Call `list_reports` to discover all configs, or `get_workspace_context` for all entities
2. Loop through each requested report/entity combination
3. Output each as a separate file, or combine into a single file with an `entity` and `report` column if the user prefers a unified dataset
4. Report progress as you go — "Exported 3 of 7 reports..."

## Edge Cases

- If `list_reports` returns no matching config, tell the user what configs exist and offer to `build_report` ad-hoc instead
- If the report data is empty for the requested period, say so clearly rather than outputting an empty file
- If the user asks for a period that doesn't exist in `get_workspace_context`, flag it and suggest the closest available period
