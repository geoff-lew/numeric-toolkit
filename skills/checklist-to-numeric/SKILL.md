---
name: checklist-to-numeric
description: Convert any close-checklist spreadsheet (FloQast, BlackLine, Trintech, Workiva, or a custom xlsx/csv) into a Numeric-ready import workbook. Trigger whenever the user wants to migrate a close checklist into Numeric, says anything like "convert FloQast to Numeric", "migrate BlackLine checklist", "import my close checklist into Numeric", "turn this spreadsheet into Numeric tasks", "map my checklist to Numeric", or uploads any xlsx/csv that looks like a close checklist (rows are tasks; columns include some form of task name, frequency, preparer, deadline). Also triggers for FloQast exports specifically (FloQast_Checklist_Template_*.xlsx). The script auto-detects column mappings from a synonym table and accepts explicit --map overrides when headers are unusual.
---

# Checklist → Numeric Converter

Convert a close-checklist spreadsheet (xlsx or csv, any source tool) into a two-tab Numeric-ready xlsx. Clean, validated tasks land on `Numeric Import`; anything that needs human judgment lands on `Needs Review` with the specific issue called out.

## When to run

The user has a close checklist in a spreadsheet and wants to bring it into Numeric. Sources this handles out of the box:

- **FloQast** — `FloQast_Checklist_Template_*.xlsx` (columns: `FQ Folder`, `Description`, `Frequency`, `Preparer`, `Preparer Deadline`, `Reviewer`, `Reviewer Deadline`, `Tags`).
- **BlackLine** — task exports with `Process`, `Task Description`, `Frequency`, `Prepared By`, `Reviewed By`, etc.
- **Trintech / Cadency** — similar shape with `Cycle` or `Workstream` as the category.
- **Generic / homegrown** — any xlsx or csv with a recognizable set of headers.

If the source uses an unusual header (e.g. `Activity` instead of `Description`), the script either auto-detects via a synonym list or accepts an explicit `--map field=header` override.

## Workflow

1. **Peek at the headers.** Before running the script, run it with `--list-headers` (or `--dry-run`) so you can see both the source headers and the auto-detected mapping. This is important because the user's source file may have unexpected columns and it's much cheaper to confirm the mapping upfront than to discover a mismapping after the fact.

2. **Confirm the mapping with the user if anything is ambiguous.** In particular:
   - If any *required* field (`category`, `task_name`, `frequency`) wasn't detected, ask the user which column to use.
   - If the auto-detected `task_name` could plausibly be a different column (e.g. both `Description` and `Task` exist), surface the guess and ask.
   - If a `preparer_deadline` column is present but values look like calendar dates instead of business-day offsets, flag this — the script assumes BDs.

3. **Run the converter.** Example invocations below. Always show the user the `computer://` link to the output xlsx and the summary (mapping, row counts, Type/Frequency breakdown, Needs Review breakdown, multi-assignee drop count).

4. **If the user uploaded the file but no explicit output path**, put the xlsx in the outputs directory so it opens with a click.

## How to run

```bash
python3 scripts/convert.py <input.xlsx|csv> [output.xlsx] [options]
```

Common options:

```
--sheet NAME          Read a specific sheet (xlsx only)
--map FIELD=HEADER    Override auto-detection. Repeatable.
--list-headers        Show the file's headers and exit
--dry-run             Detect columns, print the mapping, don't write output
```

Field names for `--map`: `category`, `task_name`, `frequency`, `preparer`, `preparer_deadline`, `reviewer`, `reviewer_deadline`, `tags`.

**Examples:**

```bash
# FloQast — headers match the synonym table, no overrides needed
python3 scripts/convert.py FloQast_Checklist_Template_Acme.xlsx

# BlackLine — mostly auto-detects, but force task_name just to be safe
python3 scripts/convert.py blackline_export.xlsx --map task_name="Task Description"

# Homegrown — explicitly map the unusual columns
python3 scripts/convert.py close_tracker.xlsx \
  --map category="Process" \
  --map task_name="Activity" \
  --map preparer="Owner" \
  --map preparer_deadline="Due BD"

# Just inspect without writing
python3 scripts/convert.py mystery_file.xlsx --dry-run
```

## What the script does, and why

### Column detection

The script ships with a synonym table for each Numeric field. Matching is case- and whitespace-insensitive. When multiple synonyms match, the first one in the list wins (so e.g. `Description` wins over `Task` for `task_name`).

| Numeric field | Common source headers |
|---|---|
| `category` | FQ Folder, Folder, Group, Section, Category, Area, Process, Process Area, Cycle, Workstream, Close Area, Module |
| `task_name` | Description, Task, Task Name, Task Description, Name, Activity, Step, Item, Procedure, Control Description, Control, Close Task |
| `frequency` | Frequency, Cadence, Schedule, Freq, Recurrence |
| `preparer` | Preparer, Preparer Email, Assignee, Owner, Prepared By, Responsible, Assigned To, Performer |
| `preparer_deadline` | Preparer Deadline, Prep Due, Prep BD, Preparer Due, Due Date, Due BD, Business Day, BD, Day, Offset |
| `reviewer` | Reviewer, Reviewer Email, Approver, Review By, Reviewed By, Secondary Reviewer |
| `reviewer_deadline` | Reviewer Deadline, Review Due, Rev BD, Reviewer Due, Approval Due |
| `tags` | Tags, Labels, Notes, Remarks |

The mapping used is always printed in the summary so the user can sanity-check it.

### Output schema

Two tabs in one xlsx:

**`Numeric Import`** — ready to save as CSV and import. Columns:

```
Category | Task Name | Frequency | Type | Description | Preparer | Reviewer | Prep. Due | Rev. Due
```

**`Needs Review`** — rows that couldn't be cleanly mapped. Same columns, plus `Source Row` and `Issues` at the left.

### Numeric's import rules (hard constraints the script enforces)

- Required columns: `Category`, `Task Name`, `Frequency`.
- `Task Name` ≤ 350 characters — longer names are truncated and the full text moves to `Description`, with a flag routed to Needs Review.
- `Frequency` must be exactly `Monthly`, `Quarterly`, or `Annually`.
- `Type` must be `Task` or `Journal Entry` (blank defaults to Task).
- One preparer and one reviewer per task — multi-assignee rows collapse to the first; the drop count surfaces in the summary so the user can duplicate tasks post-import if dual sign-off is needed.
- Due dates (`Prep. Due`, `Rev. Due`) are business-day offsets. BD=0 is not valid in Numeric, so the script silently coerces BD=0 to BD=1. Preparer due must be within ±65, reviewer due within ±45 — anything outside that range → Needs Review. If the Preparer (or Reviewer) slot is empty, the matching due-date cell is left blank; a due date never appears without an assignee.

### Category

Strip a leading numeric prefix when followed by a separator: `"01 Cash and Cash Equivalents"` → `"Cash and Cash Equivalents"`. This is safe for names like `"401k Administration"` because the regex requires a real separator after the digits.

### Task Name / Description

Preserve the original full text — don't split on `" - "`. GL account numbers and BD markers often appear after dashes in close checklists and splitting creates false parent/child relationships (e.g. `"23105"` as a parent of `"BD -5"`). Concrete handling:

- name ≤ 120 chars → goes in `Task Name`, `Description` blank
- 120 < name ≤ 350 → goes in `Task Name`, full text mirrored to `Description` for visibility
- name > 350 → truncated in `Task Name` with `...`, full in `Description`, flagged

### Frequency

| Source | Numeric |
|---|---|
| `Monthly` | `Monthly` |
| `Quarterly` | `Quarterly` |
| `Annual`, `Annually`, `Yearly` | `Annually` (cosmetic normalization, stays on main tab) |
| `Weekly` | expanded — see weekly section |
| `Custom: ...` with ≥ 6 months | `Monthly`, routed to Needs Review |
| `Custom: ...` with 2–5 months | `Quarterly`, routed to Needs Review |
| `Custom: ...` with 1 month | `Annually`, routed to Needs Review |
| blank / unknown | defaults to `Monthly`, routed to Needs Review |

Custom-mapped rows always go to Needs Review so a human confirms the call.

### Weekly expansion

Numeric doesn't have a native `Weekly` frequency, but checklist tasks tagged weekly need to run four times a month. The script explodes a single source row with `Frequency=Weekly` into **four `Monthly` rows** at `BD+5`, `BD+10`, `BD+15`, `BD+20`. Task names get `" - Week 1"` through `" - Week 4"` suffixes.

Reviewer due for each week preserves the original prep→rev gap if the source had one. If the source had no reviewer, the week rows leave reviewer due blank.

### Type (Task vs. Journal Entry)

Default `Task`. If the source `tags` cell contains `#JE`, `#je`, or `#journal_entry` (case-insensitive), set `Type = Journal Entry`. The tags column itself is not carried into the output.

### Preparer / Reviewer (single slot each)

Split the source cell on `;` or `,`. Keep the first value, drop the rest. The count of rows with dropped extras is reported in the summary so the user knows whether to duplicate any tasks post-import.

### Due dates

Source deadlines can look like `4`, `4; 4`, `3; 5`, `20*` (trailing `*` is a weekend-adjustment marker — strip it). Take the first value, coerce to integer.

Validation:

- BD=0 → coerced to BD=1 silently (Numeric doesn't accept zero)
- No Preparer → `Prep. Due` cleared; no Reviewer → `Rev. Due` cleared
- `|Prep. Due|` > 65 → Needs Review
- `|Rev. Due|` > 45 → Needs Review
- Non-numeric / unparseable → kept as-is, no flag (rare, user will spot it in the output)

### Row order

Preserve source order so folder groupings stay intact and diffs against the original export stay trivial.

## What the user sees

Every run prints the column mapping first, then the summary:

```
Column mapping:
  category             ← 'FQ Folder'
  task_name            ← 'Description'
  frequency            ← 'Frequency'
  preparer             ← 'Preparer'
  preparer_deadline    ← 'Preparer Deadline'
  reviewer             ← 'Reviewer'
  reviewer_deadline    ← 'Reviewer Deadline'
  tags                 ← 'Tags'
  Ignored headers: ['Preparer Estimated Time (minutes)', 'Reviewer Estimated Time (minutes)']

✓ 288 output rows (weekly source tasks expanded: 0 → 0)
  → 268 clean rows on 'Numeric Import' tab
  → 20 rows routed to 'Needs Review' tab
  ⚠ 8 rows had 2+ preparers/reviewers — kept first only
    (duplicate the task in Numeric post-import if dual sign-off is required)

  Type:          Task 160  |  Journal Entry 128
  Frequency:     Monthly 191  |  Quarterly 73  |  Annually 4

  Needs Review breakdown:
     14  Frequency needs review
      3  Reviewer due is zero
      3  Preparer due is zero
      2  missing Preparer

  Output: .../Acme_Numeric_Import.xlsx
```

The mapping + summary is the deliverable — the xlsx is the artifact, but the summary is how the user decides whether to trust the import and where to focus their Needs Review pass.
