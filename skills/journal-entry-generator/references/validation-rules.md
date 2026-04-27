# Validation Rules

All checks run via `scripts/validate_je.py`. 14 rules total.

## Mathematical (rules 1-4)

1. **DR = CR** — the entry must balance. Zero tolerance.
2. **Source tie-out** — JE total must equal source document total. Mode depends
   on JE type: `total_debit`, `net`, or `allocation_base`.
3. **FX consistency** — all lines use the same exchange rate.
4. **Rounding** — the largest line absorbs penny differences. The Calc layer
   must show the adjustment explicitly.

## Structural (rules 5-10)

5. **Account populated** — every line has a valid Account value.
6. **Form-required fields** — Department, Class, Location populated per
   `form_required_fields` in the input JSON.
7. **Single-sided lines** — no line has both Debit and Credit values.
8. **Date consistency** — all lines have the same post date.
9. **Subsidiary consistency** — standard JEs impact one subsidiary only.
   Multiple subsidiaries → must be intercompany (4-line minimum with
   clearing account).
10. **External ID format** — matches the configured pattern.

## Business logic (rules 11-12)

11. **No BS items expensed** — deposits, prepaid items must hit BS accounts,
    not P&L.
12. **Expense direction** — expenses should be debits. Credits on expense
    accounts → confirm labeled as reversal in memo.

## Type-specific (rules 13-14)

13. **Reclass account-level net** (Type 3) — department reclass must leave
    account balance unchanged.
14. **Entity tab balance** (Type 4) — each entity's lines balance
    independently.
