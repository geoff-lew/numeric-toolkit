# Detection Logic & Parsing Guidance

## JE Type Detection

Detect intent first, format second. Work through these steps in order — stop
at the first confident match.

### Step 1 — User or task intent

Check the Numeric task name and any user instructions first:
- "reclass" / "reversal" / "fix" → Type 3
- "allocate" / "distribute" / "split" → Type 4
- "book this invoice" / "record" → Type 1
- "usage" / "export" / "platform" → Type 2

### Step 2 — Filename signals

| Filename pattern | Likely type |
|-----------------|-------------|
| "invoice", "bill", "statement" | Type 1 |
| "export", "usage", "rewards" | Type 2 |
| "GL", "dump", "trial balance", "TB" | Type 3 |
| "allocation", "reclass", "schedule", "amort" | Type 4 |

### Step 3 — Header row signals

| Column pattern | Type |
|---------------|------|
| "Bill to", "Total due", "Payment terms", "Invoice #" | Type 1 |
| "Usage", "Quantity", "Unit price", single summary total | Type 2 |
| "Transaction ID", "Accounting Period", "Debit"/"Credit" columns | Type 3 |
| Multiple entity tabs, formula-driven DR/CR, NS column names | Type 4 |

### Step 4 — Ask the user

If still ambiguous, present the top two candidates with reasoning.

## Parsing guidance by type

**Type 1 — Source Document:** Find the line item table. Extract description,
amount, currency. One Entry per invoice per entity.

**Type 2 — Platform Export:** Line-item detail → one line per item or aggregate
by category. Single total → one DR + one CR. One Entry per period.

**Type 3 — GL Dump:** Map columns to Transaction ID, Date, Account, Department,
Debit, Credit, Memo. One Entry per derivative action (each reclass, each
reversal, each FX remeasurement gets its own).

**Type 4 — Allocation Workbook:** Read the output tabs — the workbook IS the
calculation engine. One Entry per entity tab (allocation reclass) or per
sub-ledger item (schedule-driven).

## Tie-out mode by type

| Type | tie_out_mode | Why |
|------|-------------|-----|
| 1 | `total_debit` | Source total = sum of debits |
| 2 | `total_debit` | Source total = sum of debits |
| 3 | `net` | Source is the net impact being reclassed/reversed |
| 4 | `allocation_base` | Source is the base amount being allocated |
