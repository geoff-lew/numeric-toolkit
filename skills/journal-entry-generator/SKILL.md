---
name: journal-entry
description: >
  Generates and posts NetSuite journal entries from source documents, platform
  exports, GL dumps, and allocation workbooks. Pulls pending JE tasks from
  Numeric, parses uploaded files, classifies line items, builds formula-first
  Excel workpapers, validates DR=CR balance, outputs NetSuite CSV import files,
  and optionally posts directly to NetSuite via ns_createRecord MCP. Trigger
  whenever the user mentions "journal entry", "JE", "book this invoice",
  "reclass entry", "record this", "post to NetSuite", "post this JE",
  "post the journal entry", "post entries", "submit JE", "process this invoice",
  "month-end entries", "monthly entries", "create the entry", "import to
  NetSuite", "build the JE", "prepare entries", "generate a JE", "need to book",
  "book this to NetSuite", or any reference to creating, generating, booking,
  or posting journal entries from source documents.
---

# Journal Entry Skill

Generates NetSuite journal entries from source documents. One task at a time —
pull from Numeric checklist, generate the JE, post, submit, repeat.

## Flow

1. Connect to Numeric workspace (Phase 0)
2. Pick a task from the checklist (Phase 1)
3. Parse file, generate JE, validate, build workpaper (Phase 2)
4. Review with user, generate files, optionally post to NS (Phase 3)
5. Submit task in Numeric, save learned context (Phase 4)

## Reference files

Read these as needed — not upfront:

- **NetSuite schema**: [references/netsuite-je-schema.md](references/netsuite-je-schema.md)
- **Classification rules**: [references/classification-rules.md](references/classification-rules.md)
- **Detection logic**: [references/detection-logic.md](references/detection-logic.md)
- **Validation rules**: [references/validation-rules.md](references/validation-rules.md)
- **NS posting errors**: [references/ns-posting-errors.md](references/ns-posting-errors.md)

## JE types

| Type | Intent | Example inputs |
|------|--------|----------------|
| 1 — Source Document | Record a transaction | Vendor invoice, interest statement |
| 2 — Platform Export | Record consumed services | Cloud usage export, rewards CSV |
| 3 — GL Dump | Fix or extend existing data | P&L GL dump for reclass/reversal/FX |
| 4 — Allocation Workbook | Distribute an allocation | Commission reclass, sublease schedule |

## Phase 0: Connect to workspace

```
1. list_workspaces → match customer → set_workspace
2. get_workspace_context → entities, open period, users
```

## Phase 1: Pick a task

### Step 1a — Pull open JE tasks

```
list_tasks(
  period_id = {open_period_id},
  task_type = "journal_entry",
  status = "PENDING"
)
```

### Step 1b — Present tasks to user

Show tasks in a table with assignees, statuses, and due dates. Flag overdue.
Ask: **"Which task do you want to work on?"**

One task at a time. Wait for their answer.

### Step 1c — Read task context and ask for file

Read the task description and comments via `get_task_comments`. The description
and prior comments may contain instructions from previous runs (subsidiary,
account preferences, classification notes, External ID pattern, etc.). Use
these as your starting context.

Ask:
- "Upload the supporting file for this task."
- Any clarifying questions that aren't answered by the task description
  (e.g., entity if multi-subsidiary, aggregation level)

Always require a file upload.

After this task completes (through Phase 4), return to Step 1b for the next
task.

## Phase 2: Analyze & Generate

### Step 2a — Parse & classify

- Parse the file, identify column structure and data layout
- Detect JE type per [references/detection-logic.md](references/detection-logic.md)
- Record the column mapping for the workpaper builder:
  `{"amount": "D", "category": "B"}` (actual columns from the file)
- Classify line items per [references/classification-rules.md](references/classification-rules.md)

### Step 2b — Generate JE lines

- Generate External ID. Default: `JE-{CUSTOMER}-{YYYYMM}-{SOURCE}-{SEQ}`
  (zero-padded to 3 digits). Use any pattern specified in the task description.
- Populate fields per [references/netsuite-je-schema.md](references/netsuite-je-schema.md)
- Rounding: largest line absorbs penny difference, visible in Calc layer
- Intercompany: if lines cross subsidiaries → 4-line structure with clearing
  account. Pass `--ic` to workpaper builder in Step 2d.
- Embed task ID in memo: `[Task #{task_id}] {description}`

### Step 2c — Validate

```bash
python scripts/validate_je.py je_output.json
```

Set `tie_out_mode` in the input JSON based on JE type:
- Type 1, 2: `total_debit`
- Type 3: `net`
- Type 4: `allocation_base`

If validation fails: fix and re-validate. Do not proceed with a failing JE.

### Step 2d — Build workpaper

```bash
python scripts/build_workpaper.py \
  --source source_data.json \
  --je je_lines.json \
  --column-map '{"amount": "D", "category": "B"}' \
  --output workpaper.xlsx
```

Add `--ic` for intercompany entries.

Three-layer formula-first workbook:
1. **Source** — raw parsed data, no formulas
2. **Calc** — formulas transforming source into JE amounts
3. **JE** — every amount is a formula pointing to Calc. Balance check at bottom.

#### Known limitations of `build_workpaper.py`

Build the workpaper manually (see "Manual workpaper pattern" below) if any
of these apply:

- **Duplicate accounts across JE lines**: The Calc tab dedupes by account
  name, collapsing multiple JE lines that share an account (e.g. three
  benefits lines all hitting `6130`) into a single Calc row. The missing
  lines compute to 0.
- **Descriptive memos**: The Calc tab's SUMIFS matches JE line memo ==
  Source category column. If the memo is descriptive (e.g. "Salaries — 5
  EOR employees") rather than an exact category key (e.g. "Salary"),
  SUMIFS returns 0 for every line.
- **Multi-dimension filters**: If the split needs two or more filter
  dimensions (employee + category, category + description-contains, etc.),
  the single-SUMIFS generator can't express it.
- **No cached values**: openpyxl writes the formula text but leaves the
  cached-value slot empty. See "Always write cached values" below.

#### Always write cached values alongside formulas

openpyxl writes formula text but does NOT compute values. Many renderers
(chat previews, Quick Look, Drive preview, any viewer without a calc
engine) read cached values and display blanks when they're absent — even
though the formulas are correct and would recalc on open in Excel/Sheets.

**Always compute amounts Python-side and write both the formula and the
cached value**, so the workpaper renders correctly everywhere AND retains
the formula audit trail.

Simplest robust approach: **use xlsxwriter for the final write**. It has
first-class support for cached formula results:

```python
import xlsxwriter
wb = xlsxwriter.Workbook('workpaper.xlsx')
ws = wb.add_worksheet('JE')
cached_value = 103000.00  # compute Python-side
ws.write_formula(
    row, col,
    '=SUMIFS(Source!$D$2:$D$53,Source!$B$2:$B$53,"Salary")',
    cell_format,
    cached_value,  # this is what viewers without a calc engine display
)
```

If staying on openpyxl, compute the value Python-side and set
`cell.value = cached_value` instead of the formula when the renderer won't
recalc — you lose the formula audit trail but the file renders correctly.
Don't leave formulas without cached values in a deliverable.

#### Manual workpaper pattern (when the script doesn't fit)

For any JE where the script's assumptions don't hold, build the workpaper
directly with xlsxwriter:

1. **Source tab**: write raw inputs, one row per source line.
2. **Calc tab**: one row per JE line (not per unique account). Columns:
   Line #, Account, DR/CR, filter dimensions (Employee, Category,
   Description pattern), Amount, Rounding, Final.
   - Amount is a SUMIFS that only includes the filter dimensions actually
     needed — never pass `"*"` as a SUMIFS criterion (Google Sheets and
     strict Excel configs treat `"*"` as literal, not wildcard). If a
     dimension shouldn't filter, omit that criterion entirely.
   - Pass the Python-computed value as the cached result.
3. **JE tab**: one row per JE line; Debit/Credit each reference the
   matching Calc row's Final column. Bottom rows: SUM(Debits),
   SUM(Credits), difference, "should be 0.00" label.

#### Verify before presenting to the user

After writing the file, open it with `openpyxl.load_workbook(path,
data_only=True)` and read cell values. If any formula cell comes back as
`None`, the cached value wasn't written and the preview will show blanks.
Fix before handing off — do not trust the recalc-on-open path.

## Phase 3: Review & Post

### Present for review

Show: task name, External ID, total DR/CR, line count, validation flags.
Link to the workpaper.

User can: approve, adjust (re-runs Phase 2), or skip this task.

After approval, ask: "Post directly to NetSuite, or just generate the files?"

### Always generate files

Every run produces both:
1. **CSV** — flat file with `Journal Entry -Line:` prefixes, ready for NS Import
   Assistant. See [references/netsuite-je-schema.md](references/netsuite-je-schema.md).
2. **Excel workpaper** — the three-layer workbook from Step 2d.

### Post to NetSuite (if user opts in)

Call `ns_createRecord` with record type `journalentry`:

```
ns_createRecord(
  type: "journalentry",
  fields: {
    "externalid": "JE-ACM-202602-EORVENDOR-001",
    "trandate": "2026-02-28",
    "subsidiary": { "value": "10" },
    "memo": "[Task #tsk_xxx] Close AP",
    "line": [
      {
        "account": { "value": "6122" },
        "debit": 149345.38,
        "department": { "value": "520" },
        "memo": "Salaries — 45 employees"
      },
      {
        "account": { "value": "2100" },
        "credit": 149345.38,
        "department": { "value": "520" },
        "memo": "AP offset"
      }
    ]
  }
)
```

On success: capture NS internal ID. Report: "Posted as NS JE #12345."

On failure: consult [references/ns-posting-errors.md](references/ns-posting-errors.md).
Surface the raw error and suggested fix to the user.

## Phase 4: Submit & Save context

### Submit to Numeric

1. **Role check** — is authenticated user the assignee?
   - Yes → comments + `submit_task` with `role: ASSIGNEE`
   - No → comments only, skip submit. Notify user.

2. **Comment** — JE detail + observations:
   ```
   $125,000.00 — EOR Vendor Feb 2026 Invoice (NS JE #12345). 19 DR + 1 CR.
   Refundable deposits ($10,000) classified as asset (1425), not expense.
   ```

### Save learned context

Check if the task description already has a `## JE Instructions` section. If
it does, update only the fields that changed — do not delete or overwrite the
rest of the description. If it doesn't exist yet, append it to the end of the
existing description via `edit_task`.

Fields to include (only those that are relevant to this task):

```
## JE Instructions (auto-saved)
Subsidiary: 10 Acme Corp US
Use account numbers: yes
External ID: JE-ACM-{YYYYMM}-CLOSEAP-{SEQ}
Form requires: Department (line), Location (line)
Account 6122 for admin fees, split by dept
Source file: column D = amount, column B = category
IC clearing account: 2199
```

Preserve everything else in the task description. Only touch the
`## JE Instructions` block.
