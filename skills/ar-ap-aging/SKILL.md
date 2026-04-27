---
name: ar-ap-aging
description: Build an AR (Accounts Receivable) or AP (Accounts Payable) aging from a Numeric workspace. Pulls transaction lines, classifies trade vs journal, FIFO-matches reductions against oldest open items, buckets open balances (Current/1-30/31-60/61-90/90+), and produces a 2-sheet Excel workbook with a GL reconciliation row. Use whenever the user says "AR aging", "AP aging", "aged receivables", "aged payables", "collections report", "who owes us money", "who do we owe", "vendor aging", "customer aging", "age the AR", "age the AP", "bills past due", or any request for an aging schedule out of Numeric.
---

# AR / AP Aging — Lean

One skill, two modes. The FIFO math is identical; only the trade types, labels, and a couple of filters change.

Five load-bearing pieces:
1. **Mode** (AR or AP) + as-of date + AR/AP account
2. Transaction pull (regime-aware, deduped)
3. Trade vs journal classification
4. FIFO aging into buckets
5. GL reconciliation row

Everything else is optional polish — don't add it unless the user asks.

## Step 0 — Ask the user

**Always ask upfront:**

- **AR or AP?** Don't guess from context.
- **Workspace** — which Numeric workspace.
- **As-of date** — default to last month-end if unspecified.
- **Which account?** — asked in Step 2 after listing the candidates in the chosen workspace. Don't auto-pick even if one looks "primary".
- **DTC filter** (AR only) — default on (exclude counterparties starting `Cust:`). Only ask if the user hints at consumer scope.

## Step 1 — Setup

```
list_workspaces → set_workspace (the one the user named)
get_workspace_context  (period list + gl_connection_id)
```

## Step 2 — Ask which account to age

```
list_financial_accounts
```

**AR mode:** filter `category=="ASSET"` AND name matches `/receivable|AR|A\/R/i`.
**AP mode:** filter `category=="LIABILITY"` AND name matches `/payable|AP|A\/P/i`.

Show the user the filtered list — account code, name, external_id — and ask which one they want aged. Don't auto-pick. Common cases where the "obvious" choice is wrong:

- Trade AR vs intercompany AR vs other receivables
- Trade AP vs credit card payable (AmEx, Chase) vs intercompany AP
- Separate AP accounts per subsidiary

The only time to skip the prompt is when the filter returns exactly one account.

For reference: NetSuite's default trade accounts are usually `external_id=119` (AR, "Accounts Receivable") and `external_id=111` or `112` (AP, "Accounts Payable") — useful as a hint in the prompt, but not a default.

Capture the GL balance of the chosen account at the as-of date — needed for the reconciliation row in Step 5.

## Step 3 — Pull transaction lines (regime-aware)

`query_transaction_lines` needs a report_id + row_key. Any BS report containing the target account works. Call `get_report_data` on a BS flux report to confirm the row exists and capture the row key. Key format is typically `grp_XXXXX/<external_id>` or just `<external_id>`; if one fails, try the other with `type: "path"`.

### Lookback window

**Default: 12 months back from the as-of date.** Covers normal DSO/DPO, slow-pay scenarios, and most stale items before write-off. Don't extend unless the GL reconciliation in Step 5 shows a material gap concentrated at the edge of the lookback.

The workbook is labeled with the 12-month lookback so the user knows the coverage boundary.

### Strategy selection

First call: 12-month window ending at the as-of date.

- Returns **< ~8K rows** → low-volume regime. You're done. Sample = truth.
- Returns **exactly 10K rows or times out** → high-volume regime. Switch to chunked pulls:
  - Query single month-ends (last day of each closed month).
  - Walk back month by month covering the lookback window.
  - Dedupe by line `id` across all responses.
  - Expect an unreconciled gap. Surface it honestly in Step 5.

Save merged, deduped rows to a TSV in the working directory. **Include the `normal_amount` column** (see Sign convention below).

### Sign convention

The script reads `normal_amount`, not `net_amount`. `normal_amount` is oriented to the account's natural direction — positive means balance increases, negative means balance decreases:

- AR: `CustInvc` → positive, `CustPymt` / `CustCred` → negative
- AP: `VendBill` → positive, `VendPymt` / `VendCred` → negative

`net_amount` uses signed DR/CR, which flips for AP (credits come back negative). Using `normal_amount` keeps the FIFO math identical across AR and AP.

## Step 4 — Classify

Per row, by mode:

**AR mode:**
- `transaction_type` in `{CustInvc, CustPymt, CustCred}` AND counterparty is named (not `Cust:…` when DTC filter is on, not empty) → **Trade**
- `transaction_type` in `{Journal, FxReval}` → **Journal** (exclude from aging)
- Else → drop

**AP mode:**
- `transaction_type` in `{VendBill, VendPymt, VendCred}` AND counterparty is named (non-empty) → **Trade**
- `transaction_type` in `{Journal, FxReval}` → **Journal** (exclude from aging)
- Else → drop

Journals are excluded from aging, not aged separately. Aging a journal entry like a customer invoice or vendor bill produces misleading days-past-due.

**Note on `ExpRept` (AP only):** some NetSuite configs route employee expense reimbursements through AP. If the workspace uses this pattern and the user wants them aged alongside bills, add `ExpRept` to the AP trade types. Default is to exclude.

## Step 5 — FIFO age and build workbook

Pass the classified TSV and a config JSON to `scripts/build.py`. Config fields:

```json
{
  "mode": "AR",
  "company_name": "Acme",
  "as_of_date": "2026-03-31",
  "gl_balance": 20290371.32,
  "output_path": "/path/to/Acme_AR_Aging_2026-03-31.xlsx",
  "txn_tsv_path": "/path/to/transactions.tsv",
  "b2b_only": true
}
```

`mode` must be `"AR"` or `"AP"`. `b2b_only` is only honored when `mode=="AR"`.

The script:
- Dedupes by id, classifies, drops post-as-of-date rows
- Per counterparty: sorts open items oldest → newest, pools reductions (payments + credits), consumes oldest FIFO, ages remaining balances
- Unapplied credits / overpayments land in Current as negative
- Output: **Summary** sheet (GL balance, bucket totals, GL reconciliation row with unreconciled gap highlighted) + **Aging by Customer** or **Aging by Vendor** sheet (counterparty × buckets, sorted by total)

## Step 6 — Deliver

Give the user a `computer://` link to the workbook and a 3-line read:
- Total open AR/AP + largest single exposure
- Anything aged 90+ worth flagging (for AR: collections risk; for AP: vendor relationship damage, late fees, potential stop-ships)
- If the reconciliation gap is material, say so and recommend pulling NetSuite's native A/R or A/P Aging Detail for the authoritative view

That's it. If the user asks for per-item detail, a non-trade tab, or early-pay discount analysis, add them — but don't ship them by default.

## Note on aging basis

This skill ages by **transaction date** (`as_of_date − transaction_date`), matching how Numeric's data is structured. For AP specifically, aging by **due date** would be more accurate since bills have explicit payment terms (Net 30, Net 60, etc.). If Numeric ever exposes `due_date` in the transaction lines output, update the script to use `as_of_date − due_date` for AP. Until then, document the basis in the workbook.
