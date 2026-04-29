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

## Report data routing

GL data must be pulled through this ordering. Do not skip steps. `build_report` is unreliable and is treated as a last resort.

1. **Call `list_reports` first.** Inspect saved configurations for matches by `statement_type`, comparison, and name.
2. **Use `get_report_data(configuration_id, period_id)` for any matching saved report.** If multiple saved reports plausibly match, show the user the top 2–3 and let them pick — do not silently pick.
3. **Only fall back to `build_report` when no saved config can serve the need.** State the fallback explicitly to the user, and why.
4. **Validate the `build_report` response.** If it returns no data rows, or rows where every balance is zero/null, stop. Do not produce a partial or empty output.
5. **On `build_report` failure, ask the user.** Show them the saved configs from step 1 and ask which one to use instead, or ask for explicit instruction (different period, different entity, manually-specified report ID, abort).

When step 3 is reached, also call `get_workspace_context` to get the entity list and `gl_connection_id` values, and supply `statement_type`, `as_of_year`, and `as_of_month` to `build_report`.

## Selecting the Right Comparison Type

Match the user's request to the `comparison` parameter (used either to pick the right saved report or, as a last resort, to pass to `build_report`):

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

- If `list_reports` returns no matching config, tell the user what configs do exist and ask whether to fall back to `build_report` or to pick one of the existing configs anyway
- If `build_report` returns empty or all-zero data, do not write a file — show the user the saved configs from `list_reports` and ask which one to use instead, or ask for further instruction
- If the report data is empty for the requested period, say so clearly rather than outputting an empty file
- If the user asks for a period that doesn't exist in `get_workspace_context`, flag it and suggest the closest available period
