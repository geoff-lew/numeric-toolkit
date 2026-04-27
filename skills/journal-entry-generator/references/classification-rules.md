# Classification Rules

Reference for classifying line items when the account mapping isn't obvious
from the file or task context.

## P&L vs Balance Sheet

Classify the balance sheet impact before assigning an account.

| Item | Classification | Why |
|------|---------------|-----|
| Refundable deposits, security deposits | Asset (BS) | Will be returned; not consumed |
| Prepaid items, annual licenses | Asset (BS) | Benefit extends beyond current period |
| Signing bonuses | Expense (P&L) | Consumed immediately |
| Benefits, salaries, commissions | Expense (P&L) | Current period cost |
| Platform / SaaS fees | Expense (P&L) | Current period cost |

## Nature over vendor label

Classify by what the spend IS, not what the vendor calls it.

| Vendor description | Actual nature | Account guidance |
|-------------------|---------------|-----------------|
| "Platform fees" containing background checks | Recruiting expense | 6xxx (recruiting) |
| "Service charges" containing deposit interest | Interest income | 4xxx (other income) |
| "Administrative fees" on EOR invoice | Payroll expense | 6xxx (payroll) |
| "Benefits administration" | Benefits expense | 6xxx (benefits) |

## Expense direction

Standard directions — flag if reversed:

| Category | Normal direction | Flag if |
|----------|-----------------|---------|
| Salaries, wages, commissions | Debit | Credit (unless reversal) |
| Benefits | Debit | Credit (unless reversal) |
| Revenue | Credit | Debit (unless adjustment) |
| Accrued liability | Credit | Debit (unless reversal) |

## FX handling

If source document is non-USD:
1. Identify functional currency from subsidiary config
2. Ask for exchange rate if not in task description
3. All lines in a single JE use the same rate — never mix
4. FX gain/loss goes to the FX gain/loss account (typically 8xxx)

## Intercompany

When a transaction crosses subsidiaries:
- Standard JE only impacts one subsidiary
- DR in sub A and CR in sub B → intercompany JE format
- Requires clearing account (from task description or ask user)
- Minimum 4 lines: DR+CR originating, DR+CR receiving
