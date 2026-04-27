# Ratio Definitions — Account Mapping Guide

This reference describes how to map ratio components to accounts in the chart of accounts returned by `list_financial_accounts`.

## Account Identification Strategy

1. **Category code** — most reliable. Use the account's `category` or `type` field.
2. **Name pattern** — fallback. Case-insensitive substring or regex match on account name.
3. **Ask the user** — last resort. If neither method produces a confident match, surface the ambiguity.

## Component Mappings

### Revenue
- Category: revenue, income, sales
- Name patterns: "Revenue", "Sales", "Service Income", "Subscription Revenue", "License Revenue"
- Exclude: "Other Income", "Interest Income" (these are non-operating)

### Cost of Goods Sold (COGS) / Cost of Revenue
- Category: cost_of_goods_sold, cogs, cost_of_revenue
- Name patterns: "Cost of Goods", "Cost of Revenue", "COGS", "Cost of Sales", "Direct Costs"
- Exclude: operating expenses that are not direct costs

### Operating Expenses (OpEx)
- Category: expense, operating_expense
- Name patterns: "Operating Expense", "R&D", "Research", "Sales & Marketing", "General & Administrative", "G&A", "S&M"
- Sub-grouping: if the user wants OpEx broken out, group by name prefix or department pivot

### Depreciation & Amortization (D&A)
- Category: depreciation, amortization
- Name patterns: "Depreciation", "Amortization", "D&A"
- May be embedded in OpEx line items — if not broken out separately, flag to user

### Interest Expense
- Category: interest_expense
- Name patterns: "Interest Expense", "Interest Paid", "Finance Costs"

### Tax Expense
- Category: tax, income_tax
- Name patterns: "Income Tax", "Tax Expense", "Provision for Taxes"

### Current Assets
- Category: current_asset
- Name patterns: "Cash", "Accounts Receivable", "A/R", "Inventory", "Prepaid", "Short-term"
- Key sub-components:
  - **Cash & Equivalents**: "Cash", "Cash Equivalents", "Money Market"
  - **Accounts Receivable**: "Accounts Receivable", "A/R", "Trade Receivables"
  - **Inventory**: "Inventory", "Finished Goods", "Raw Materials", "WIP"

### Current Liabilities
- Category: current_liability
- Name patterns: "Accounts Payable", "A/P", "Accrued", "Current Portion", "Short-term Debt"
- Key sub-components:
  - **Accounts Payable**: "Accounts Payable", "A/P", "Trade Payables"

### Total Debt
- Both current and non-current debt/borrowings
- Name patterns: "Loan", "Borrowing", "Debt", "Note Payable", "Line of Credit", "Term Loan"
- Exclude: trade payables, accrued liabilities (these aren't financial debt)

### Total Equity
- Category: equity, stockholders_equity
- Name patterns: "Equity", "Retained Earnings", "Common Stock", "Additional Paid-in Capital"

### Compensation / Staff Costs
- Name patterns: "Salary", "Salaries", "Wages", "Compensation", "Payroll", "Benefits", "Staff Cost"
- May be distributed across departments — sum all matching accounts

## Handling Ambiguity

When multiple accounts match a component, sum them (e.g., three revenue accounts = total revenue).

When zero accounts match:
- Try broadening the pattern (e.g., "Revenue" didn't match → try "Income")
- Check if the account is nested under a parent that matches
- If still no match, tell the user which component couldn't be found and ask them to identify the right account
