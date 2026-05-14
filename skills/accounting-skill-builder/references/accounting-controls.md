# Accounting Controls

The control taxonomy used by the Plan-phase Accounting agent (when designing controls) and the Review-phase Accounting QA agent (when validating dry-run output). Same reference, different lens.

## Two axes

**Category** — what kind of control is it.
- **Mathematical** — does it compute correctly
- **Structural** — are required fields populated and valid
- **Business logic** — does the entry match the underlying nature of the transaction
- **Type-specific** — controls that only apply to certain workflow types (intercompany, reclass, allocation, accrual)

**Scope** — does it apply everywhere or just to certain businesses.
- **Universal** — applies to any company
- **Industry-specific** — SaaS, hardware/manufacturing, services, financial services, etc.

The interviewer captures industry tag in Phase 1; both Plan and Review apply the matching pack.

## Universal controls

### Mathematical

1. **DR = CR** — entries balance. Zero tolerance.
2. **Source tie-out** — output total equals source document total. Mode varies: `total_debit`, `net`, or `allocation_base`.
3. **FX consistency** — all lines on a single entry use the same exchange rate.
4. **Rounding** — penny differences absorbed by the largest line; the adjustment is shown explicitly, not hidden.

### Structural

5. **Account populated** — every line has a valid account that resolves in `list_financial_accounts`.
6. **Form-required fields** — Department, Class, Location, Subsidiary populated per the form's requirements.
7. **Single-sided lines** — no line has both Debit and Credit values.
8. **Date consistency** — all lines on a single entry share the same post date.
9. **Subsidiary consistency** — standard JEs impact one subsidiary. Multiple subsidiaries → must be intercompany with clearing account.
10. **External ID format** — matches the configured pattern. No collisions with existing IDs.
11. **Period not locked** — the post date is in an open period, or the user has explicitly approved a back-dated post.

### Business logic

12. **No BS items expensed** — deposits, prepaid items must hit BS accounts, not P&L.
13. **Expense direction** — expenses are debits. A credit on an expense account requires a "reversal" memo.
14. **Revenue direction** — revenue is a credit. A debit on a revenue account requires an "adjustment" memo.
15. **Nature over vendor label** — classify by what the spend IS, not what the vendor calls it. "Platform fees" containing background checks is recruiting, not platform.
16. **Classification stability** — the same vendor and account combination should classify the same way across periods unless the user explicitly overrides.

### Type-specific

17. **Reclass account-level net** — department or class reclasses must leave the account balance unchanged at the account level.
18. **Entity tab balance** (intercompany) — each entity's lines balance independently.
19. **Accrual reversal** — every accrual entry has a reversal scheduled or noted in the memo.
20. **Allocation base** — allocation entries reference a documented base; the base is reproducible from data.

## Industry-specific packs

### SaaS & Software

- Capitalized software development costs hit R&D / Engineering departments only.
- SaaS COGS components (hosting, payment processing, customer success tied to delivery) belong in COGS, not G&A or Sales.
- Stock-based compensation is allocated across departments per the equity grant data, not concentrated.
- Customer Success / Professional Services costs separate from Sales.
- Deferred revenue and contra-revenue adjustments hit revenue-related departments only.

### Hardware & Manufacturing

- Inventory adjustments require physical count or systemic backup.
- Cost of goods uses standard or actual cost consistently within a period.
- Warranty accruals tied to a documented historical rate.
- Freight in vs. freight out classified separately.

### Services & Consulting

- Project-coded labor expenses tie to a project ID that resolves.
- Unbilled receivables tied to delivered hours, not contract value.
- Pass-through expenses separated from billable revenue.

### Financial Services

- Loan loss provisions follow CECL methodology (or IFRS 9 equivalent).
- Investment income classified by security type.
- Regulatory capital calculations not affected by automation outputs without a control owner sign-off.

## How Plan uses this

The Accounting agent reads the brief, identifies the workflow type (JE / reclass / accrual / reconciliation / report / commentary / other), picks the applicable controls, and writes them into `plan/accounting.md` as a numbered checklist. This list is the contract for Phase 4.

## How Review uses this

The Accounting QA agent reads the controls list from the plan, runs each numbered rule against the dry-run output, and reports pass/fail per rule with the specific evidence (the failing line, the unbalanced amount, the unresolved account). No vibe-checks.

If a control can't be evaluated automatically (e.g., "control owner sign-off"), QA flags it as "manual check required" with the specific question to ask.

## Adding new controls

When a workflow surfaces a control not in this list, the Iteration agent adds it to the universal list (if generic) or the relevant industry pack (if niche), with a one-line description and the workflow that surfaced it. This file grows with use.
