---
name: financial-metrics
description: >
  Compute and append standard financial ratios and analytic metrics to any Numeric report output.
  Three categories: profitability/margin analysis, covenant/liquidity/solvency, and operational/working
  capital. Use this skill when the user asks for "financial ratios", "margins", "gross margin",
  "operating margin", "net margin", "EBITDA", "current ratio", "quick ratio", "debt to equity",
  "interest coverage", "DSO", "DPO", "DIO", "cash conversion cycle", "working capital metrics",
  "covenant compliance", "liquidity ratios", "solvency ratios", "profitability analysis",
  "revenue per employee", "calculate ratios from the financials", "add metrics to this report",
  "what's our gross margin", "how's our liquidity", or any request for computed financial ratios
  derived from Numeric report data. Also trigger when the user references debt covenants,
  lending compliance, or financial health indicators in the context of their Numeric data.
---

# Financial Metrics

Compute standard financial ratios from Numeric report data and layer them inline on the source
financial statement. Operates in two modes depending on what the user is working from:

- **IS mode** — inline on the income statement (margins, EBITDA, staff costs)
- **BS mode** — inline on the balance sheet (liquidity, leverage, working capital days)
- **Full mode** — both sheets when the user asks for a complete financial health view

## Step 1: Pull Source Data

Most ratios require both IS and BS data:

1. Call `get_workspace_context` to get entity, period, and gl_connection_id
2. Determine the target period and entity
3. Pull IS data: `build_report` with `statement_type: "income_statement"` or `get_report_data` from a saved IS config
4. Pull BS data: `build_report` with `statement_type: "balance_sheet"` or `get_report_data` from a saved BS config
5. For trend ratios (comparing across periods), use `month_over_month_3` or `month_over_month_6` comparison
6. Call `list_financial_accounts` to get the chart of accounts for account mapping

## Step 2: Detect Mode

Infer the mode from context:

| User says / context | Mode |
|---|---|
| "add metrics to my income statement", "margins", "EBITDA", "gross margin", "operating margin" | IS mode |
| "add metrics to my balance sheet", "liquidity", "current ratio", "working capital", "DSO", "DPO" | BS mode |
| "financial health check", "all ratios", "full metrics", "complete analysis" | Full mode (both sheets) |
| Working from an existing IS output | IS mode |
| Working from an existing BS output | BS mode |

If unclear, default to Full mode and produce both sheets.

## Step 3: Identify Accounts

Map ratio components to actual chart of accounts using `list_financial_accounts`.

Use account category codes and name pattern matching. The mapping is heuristic — confirm with the user if there's ambiguity.

See `references/ratio-definitions.md` for the full account mapping logic per ratio.

### General matching strategy

1. First try category codes (most reliable): REVENUE, EXPENSE, ASSET, LIABILITY, EQUITY
2. Fall back to name pattern matching: "Revenue" / "Sales" for revenue, "Cost of Goods" for COGS, "Cash" for cash, etc.
3. If a required account can't be found, flag it: "I couldn't identify an Interest Expense account — which account should I use?"
4. When an account exists in the CoA but has $0 (e.g., Interest Expense), mark the dependent ratio as N/A with a note
5. When no Inventory accounts exist, mark DIO as N/A — Quick Ratio equals Current Ratio in this case

## Step 4: Compute Ratios

Compute only the ratios the user requests. If they say "all ratios" or "financial health check", compute all three categories.

### Category 1: Profitability / Margin Analysis

| Metric | Formula | Requires |
|---|---|---|
| Gross Margin | (Revenue - COGS) / Revenue | IS |
| COGS as % of Revenue | COGS / Revenue | IS |
| Operating Margin | Operating Income / Revenue | IS |
| OpEx as % of Revenue | Operating Expenses / Revenue | IS |
| Net Margin | Net Income / Revenue | IS |
| Staff Cost Ratio | (Payroll + Personnel) / Revenue | IS |
| EBITDA | Operating Income + Depreciation + Amortization | IS |
| EBITDA Margin | EBITDA / Revenue | IS |

For EBITDA: if D&A isn't broken out on the IS, check the Cash Flow statement or flag to the user.

### Category 2: Covenant / Liquidity / Solvency

| Metric | Formula | Requires |
|---|---|---|
| Current Ratio | Current Assets / Current Liabilities | BS |
| Quick Ratio | (Current Assets - Inventory) / Current Liabilities | BS |
| Debt-to-Equity | Total Liabilities / Total Equity | BS |
| Interest Coverage | EBIT / Interest Expense | IS |
| Debt Service Coverage | EBITDA / (Interest + Principal Payments) | IS + BS |
| Net Debt / EBITDA | (Total Debt - Cash) / Annualized EBITDA | BS + IS |

### Category 3: Operational / Working Capital

| Metric | Formula | Requires |
|---|---|---|
| DSO (Days Sales Outstanding) | (Accounts Receivable / Revenue) × Days in Period | BS + IS |
| DIO (Days Inventory Outstanding) | (Inventory / COGS) × Days in Period | BS + IS |
| DPO (Days Payable Outstanding) | (Accounts Payable / COGS) × Days in Period | BS + IS |
| Cash Conversion Cycle | DSO + DIO - DPO | Derived |
| Revenue per Employee | Revenue / Headcount | IS + external data |

For Revenue per Employee: headcount isn't in Numeric — ask the user or skip.

## Step 5: Format Output

### IS Mode — Inline on the Income Statement

Layer metrics directly below the IS line item they derive from:

| IS Line | Metric Row Below It |
|---|---|
| Total Cost of Revenue | → COGS as % of Revenue |
| Gross Profit | → Gross Margin |
| Personnel Costs | → Staff Cost Ratio |
| Total Operating Expenses | → OpEx as % of Revenue |
| Operating Income | → Operating Margin |
| Net Income | → Net Margin |

After Net Income, add an EBITDA reconciliation block:
- Operating Income + Depreciation + Amortization = EBITDA → EBITDA Margin

After EBITDA, add a **Balance Sheet Ratios** group (values pulled from BS):
- Current Ratio, Quick Ratio, Debt-to-Equity, Net Debt/EBITDA, Interest Coverage

Then a **Working Capital Metrics** group:
- DSO, DPO, DIO, Cash Conversion Cycle

Sheet name: `Income Statement + Metrics`

### BS Mode — Inline on the Balance Sheet

Layer metrics directly below the BS line item they derive from:

| BS Line | Metric Row Below It |
|---|---|
| Cash & Equivalents | → Cash as % of Current Assets |
| Accounts Receivable | → DSO (Days Sales Outstanding) |
| Inventory | → DIO (Days Inventory Outstanding) |
| Accounts Payable | → DPO (Days Payable Outstanding) |
| Total Current Liabilities | → Current Ratio, Quick Ratio, Cash Conversion Cycle |
| Total Debt (Current + Non-current) | → Net Debt, Net Debt / EBITDA |
| Total Equity | → Debt-to-Equity |
| Total Liabilities & Equity | → Interest Coverage (if IS data available) |

After the last BS line, add a **Profitability Summary** group (values pulled from IS):
- Gross Margin, Operating Margin, Net Margin, EBITDA Margin

This gives the BS reader margin context without switching sheets.

Sheet name: `Balance Sheet + Metrics`

### Full Mode

Produce both sheets in the same workbook:
1. `Income Statement + Metrics`
2. `Balance Sheet + Metrics`

### Visual formatting for metric rows (both modes)

- **Fill**: light blue/gray background (`#E8EDF3`)
- **Font**: italic, navy color (`#1F3864`)
- **Indent**: one level from the parent line
- **Trend column**: rightmost column with trend arrows:
  - `↑` = improving (green font); `↓ ⚠` = deteriorating (red font); `→` = flat
  - Direction depends on the metric — higher gross margin = good `↑`, higher D/E = bad `↑`
- **Section headers** for grouped ratio blocks: bold, colored background
  - Liquidity / BS Ratios group: green background
  - Working Capital group: yellow background
  - Profitability Summary (on BS sheet): blue background

### Number formatting

- **Percentage ratios** (margins, cost %): `0.0%`
- **Multiple ratios** (Current Ratio, D/E, Net Debt/EBITDA): `0.00x`
- **Day ratios** (DSO, DIO, DPO, CCC): `0 "days"`
- **Dollar amounts**: `#,##0;(#,##0);"-"`

### Account mapping notes

Include an "Account Mapping Notes" section at the bottom of each sheet documenting which GL accounts were used. Format as merged rows with small gray font.

## Step 6: Deliver

Output as a formatted xlsx workbook using openpyxl:
- Navy header row with white bold font
- Freeze panes at B2
- Column A = 48 width for labels, data columns = 16 width
- IS group totals: thin bottom border; Gross Profit / Operating Income / Net Income: double bottom border
- BS section totals (Total Current Assets, Total Assets, Total Liabilities & Equity): double bottom border
- MoM variance ($) and (%) columns after the period columns

File name: `{Workspace}_Financial_Metrics_{Period}.xlsx`

If the user is working with an existing report output from another skill, layer the metrics into that workbook's relevant sheet rather than creating a standalone file.

## Covenant Monitoring

If the user mentions specific covenant thresholds:

1. Compute the relevant ratio
2. Compare against the threshold
3. Flag clearly: "Current Ratio: 1.8x — COMPLIANT (threshold: 1.5x)" or "Current Ratio: 1.2x — BREACH"
4. If trending toward breach: "Current Ratio has declined from 2.1x to 1.8x over 3 months — approaching 1.5x threshold"

## Edge Cases

- **Negative EBITDA**: Net Debt/EBITDA is not meaningful — flag it explicitly.
- **Large Deferred Revenue in Current Liabilities**: Can distort Current Ratio. Add a note if Deferred Revenue > 50% of Total Current Liabilities.
- **Missing accounts**: Mark ratio as N/A with reason.
- **Multi-entity consolidation**: Use consolidated totals by default. Note which entities are included.
- **BS-only request without IS data**: DSO, DPO, DIO, Interest Coverage, and EBITDA-based ratios all need IS data. Mark as N/A and note the dependency.
