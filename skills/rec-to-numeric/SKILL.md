---
name: rec-to-numeric
user-invocable: true
description: Convert a customer's existing Balance Sheet Reconciliation assignments file into a Numeric Rec Assignment import xlsx. Pulls the chart of accounts from Numeric via list_financial_accounts, joins to a customer-supplied entity-ID file, optionally swaps old account numbers from a prior general-ledger system, maps preparer/reviewer names to emails, and emits a 3-tab xlsx that matches Numeric's Recon assignment template. Trigger when the user uploads a structured BS-Rec assignments workbook + entity-ID file and says things like "build rec import", "convert BS rec assignments", "import balance sheet recs into Numeric", or "turn this into a Numeric rec import".
---

# Rec → Numeric Import Converter

## When to use

Use this when **all three** are true:

- The customer has an existing structured spreadsheet of rec assignments (xlsx or csv) with at least Entity, Account, and Preparer/Reviewer columns.
- The customer's Numeric workspace exists and has a chart of accounts loaded.
- They want to bulk-import recs rather than create them in Numeric's UI.

## When NOT to use

- **No source file** — the customer hasn't documented assignments anywhere structured. Use Numeric's UI directly, or build a blank scaffold from the COA first.
- **Source file isn't rec assignments** — e.g. it's a journal-entry export, a flux report, or a raw COA dump. Different shape entirely.
- **One-off / under ~20 rows** — manual entry in Numeric is faster than building a spreadsheet to import.
- **No Numeric workspace yet** — set up the workspace and load the GL first.

## What the script does

Five steps:

1. **Read** the assignments file (xlsx or csv) — auto-detects the header row by scanning the first 25 rows for an `entity` and `account` column.
2. **Look up** Internal ID of Entity from an ids file.
3. **Match** each row's account number against the current Numeric COA. Order: exact description → optional alias rewrite → prefix match (handles truncated descriptions). If no match but the existing code already exists in the COA, trust it.
4. **Resolve** preparer/reviewer names to emails via a name→email CSV.
5. **Emit** a 3-tab xlsx: `Import`, `Notes & Warnings`, `Unmapped to Numeric`.

Rules baked in:
- No preparer → reviewer chain blanked (Numeric requires an owner).
- No email → matching Due Day blanked (Numeric rejects this combo).
- Multi-assignee cells: 1st preparer goes to Preparer slot; 1st + 2nd reviewer fill the two reviewer slots; anything beyond is dropped with a note.

## Workflow

1. **Confirm the workspace.** Call `set_workspace`.

2. **Pull the COA from Numeric:**

   ```
   list_financial_accounts
   ```

   Save to a CSV with columns `code,name,external_id,category,currency_code`. If the response is too large for one tool call, delegate parsing to a subagent that writes the CSV directly to outputs.

3. **Confirm column mapping** before processing. Run with `--list-headers` to see the auto-detected mapping; if anything looks off, ask the user which sheet/column to use.

4. **Run the converter** and surface the output.

## Inputs

| Flag | Required | Notes |
|---|---|---|
| `--assignments` | yes | xlsx or csv with rec rows |
| `--ids` | yes | entity → internal-ID file (xlsx or csv) |
| `--coa` | strongly recommended | CSV from `list_financial_accounts` |
| `--email-map` | strongly recommended | 2-col `name,email` CSV |
| `--aliases` | optional | 2-col `old_desc,new_desc` CSV — only needed when the BS Rec file's account descriptions don't match the current COA (e.g. legacy GL names) |
| `--property` | optional | source-column header to use as Property (default `Team`) |
| `--prep-due` / `--rev-due` / `--rev2-due` | optional | default Due Day for each role |
| `--list-headers` | flag | print headers + detected mapping and exit |

## Output

Three tabs in one xlsx:

- **Import** — rows ready to upload to Numeric.
- **Notes & Warnings** — importable but flagged (multi-assignee drops, missing emails, missing entity IDs).
- **Unmapped to Numeric** — rows whose account number isn't in the current COA. Need a real human decision before import.

Columns on the Import tab:

```
Account number | Subsidiary | Internal ID of Entity | Category | Property |
Preparer Email | Due Day of Close Preparer |
Reviewer Email | Due Day of Close Reviewer |
Second Reviewer Email | Due Day of Close Second Reviewer
```

## Run

```bash
python3 scripts/convert.py \
  --assignments  bs_rec.xlsx \
  --ids          entity_ids.xlsx \
  --coa          numeric_coa.csv \
  --email-map    emails.csv \
  --aliases      config/example_aliases.csv \
  --property     Team \
  --prep-due 3 --rev-due 5 --rev2-due 5 \
  --out          rec_import.xlsx
```
