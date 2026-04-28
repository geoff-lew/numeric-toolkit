---
name: consolidated-flux
user-invocable: true
description: >
  Consolidate flux variance commentary across entities, reports, accounts, and periods into a single
  unified view. Rolls up child-level explanations into group narratives and stitches trend commentary
  across months. Use this skill when the user asks to "consolidate flux", "combine variance commentary",
  "roll up flux explanations", "unified variance view", "merge flux from multiple reports",
  "show me all flux work in one place", "cross-entity variance summary", "trend the flux commentary",
  "what's the story across months for this account", "combine IS and BS flux",
  "roll up the child accounts into group explanations", or any request that involves combining,
  summarizing, or trending variance analysis work product from Numeric's flux module.
  Also trigger for "variance narrative", "flux summary for CFO", or "consolidated variance report".
---

# Consolidated Flux

Merge flux variance work product across multiple dimensions into a single unified view for controller or CFO review.

## Consolidation Dimensions

The user may want consolidation across one or more of these dimensions. Ask which apply, or infer from context:

### Dimension 1: Across Entities

Merge flux tasks and commentary from multiple subsidiaries into one view.

1. Call `get_workspace_context` to list all entities
2. Call `list_reports` to find flux report configs per entity
3. For each entity's flux report, call `list_tasks` with the `report_id` and target `period_id`
4. For each task, call `get_task_comments` and `get_flux_explanations` for the report
5. Merge into a single table: entity | account group | variance $ | variance % | commentary
6. Add a consolidated total row that sums across entities per account group

### Dimension 2: Across Flux Reports

Users often have separate flux reports (MoM IS, QoQ IS, MoM BS, QoQ BS). Combine them so a controller sees one queue per account regardless of which report it lives in.

1. Call `list_reports` and identify all flux-type report configs
2. For each flux report, call `list_tasks` for the target period
3. Call `get_flux_explanations` for each report
4. Merge tasks by account key — if the same account appears in both MoM IS and QoQ IS, show both variances side by side with their respective commentary
5. Output columns: account | MoM variance $ | MoM variance % | MoM commentary | QoQ variance $ | QoQ variance % | QoQ commentary

### Dimension 3: Across Accounts (Roll-Up)

Take child-account-level flux explanations and summarize into group-level narratives.

1. Pull the report data via `get_report_data` or `build_report` to get the account hierarchy
2. Pull flux explanations via `get_flux_explanations` for the report
3. Group child accounts by their parent/section (use `list_financial_accounts` category codes if needed)
4. For each group, synthesize child explanations into a single narrative:
   - Identify the top 2-3 drivers by absolute variance
   - Lead with direction + magnitude at the group level
   - Attribute to specific child accounts: "OpEx up 8% driven by headcount additions in R&D ($45K) and a one-time legal settlement in G&A ($30K)"

### Dimension 4: Across Periods (Trend)

Stitch flux commentary on the same account across multiple months to surface trends.

1. For the target account, call `get_report_row_trend` with the task_key, period_id, and appropriate column. Set `include_trailing_windows` to 3-6 depending on user preference.
2. Pull flux explanations for each of the trailing periods via `get_flux_explanations`
3. Combine into a trend narrative:
   - "Software Expense has increased 3 consecutive months (+$12K, +$8K, +$15K), driven by new vendor onboarding in Jan, license true-up in Feb, and additional seats in Mar"
4. Flag persistent trends (3+ months same direction) and inflection points

## Output Format

Default output: structured summary table with these columns:
- Account Group
- Account (if showing detail)
- Entity (if multi-entity)
- Variance $ (with period labels if multi-period)
- Variance %
- Consolidated Commentary

Write as a formatted file — use the xlsx skill for Excel output with proper formatting, or output as markdown table for quick in-chat review if the user just wants a summary.

File name: `Consolidated_Flux_{Period}.xlsx`
