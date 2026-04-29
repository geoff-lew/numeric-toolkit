---
name: audit-evidence-export
user-invocable: true
description: >
  Extract a complete activity history from a Numeric workspace for a selected close period and produce
  a formatted Excel workbook suitable for external audit evidence. Trigger this skill whenever the user
  mentions "audit evidence", "evidence of review", "activity export", "close activity", "auditor workpaper",
  "SOX evidence", "review evidence", "close history", "reconciliation history", "checklist history",
  "scrape activity from Numeric", "pull close activity", "export close details", or any reference to
  extracting who-did-what-when data from Numeric for auditors. Also trigger when the user says things
  like "get me everything from the December close for the auditors", "I need to show our auditors the
  review trail", "pull the activity log for [period]", "export reconciliation sign-offs", or "document
  the close for audit". If the user mentions Numeric in the context of auditors, SOX, evidence, sign-off
  history, or close documentation, use this skill.
---

# Audit Evidence Export

This skill connects to a Numeric workspace, lets the user choose which workspace and which
close period to pull from, then extracts every activity event (submissions, approvals,
rejections, reassignments, etc.) for **all four task types** in that period. The output is a
professional, multi-tab Excel workbook ready to hand to auditors.

## Why this exists

Auditors need timestamped proof that reconciliations were prepared, reviewed, and approved
by the right people within the close window. Manually screenshotting each task's activity
panel is tedious and error-prone. This skill automates the entire extraction so the
accounting team can produce a complete evidence package in minutes instead of hours.

## Workflow

### Step 1 — Workspace and Period Selection

Before doing any extraction, present the user with choices so they can pick exactly what
they need. Use the Numeric MCP tools in this order:

1. Call `list_workspaces` to get available workspaces.
2. Ask the user which workspace they want (if they already told you, skip the ask).
3. Call `set_workspace` with the chosen workspace ID.
4. Call `get_workspace_context` and parse out the `periods` array.
5. Present the periods to the user and ask which one to extract (if they already told you,
   match by name/slug like "dec-2025" or "December 2025" and confirm).

This selection step is important — never assume a workspace or period without confirming
with the user, unless they've already been explicit about it.

### Step 2 — Pull Task Listings

Numeric has **four distinct task types**, not two. All four must be extracted for a complete
audit evidence package:

```
list_tasks(period_id, task_type="rec_prepare_account")   → reconciliation tasks
list_tasks(period_id, task_type="custom")                 → checklist tasks
list_tasks(period_id, task_type="flux")                   → flux analysis tasks
list_tasks(period_id, task_type="journal_entry")          → journal entry tasks
```

Flux analysis tasks cover month-over-month and year-over-year variance explanations on P&L
and balance sheet lines. Journal entry tasks are items on the checklist that represent
specific journal entries to be booked — they have `task_type="journal_entry"` but use
`key_type="custom"` and `report_id="checklist"`, same as regular checklist items.

All four calls return TSV with columns: name, description, task_type, key_id, key_type,
report_id, prep_assignee, prep_status, prep_due, review_assignee, review_status,
review_due, url.

Parse the TSV into structured data. **Every row must be captured** — do not sample or
truncate. The results may be very large (400+ tasks per type, 600+ for flux) and the MCP
tool may save them to result files on disk rather than returning them inline. When that
happens, read the saved file path from the API response and parse the full file with Python
(e.g., `csv.reader` with tab delimiter). Always verify the parsed row count matches the
expected total from the API response metadata.

Also extract the user ID → name mapping from the workspace context (`users` array) so
event user IDs can be resolved to human-readable names. Save this as a JSON dict
(`{user_id: display_name}`) for use throughout the pipeline.

### Step 3 — Pull Activity Events

Call `get_task_events` for every task across all four types. The API requires `task_keys` —
an array of objects with `id` (the key_id from list_tasks), `type` (the key_type), and
`report_id`.

Because workspaces can have hundreds of tasks, batch the calls in groups of 50 task_keys
per API call. For reconciliation and flux tasks, the report_id comes from the task listing.
For checklist and journal_entry tasks, the report_id is `"checklist"`.

Launch multiple batches in parallel where possible to speed things up. Combine all returned
events into a single collection.

Each event contains:
- `event` — human-readable description ("Task completed", "Review submitted as approved", etc.)
- `action_key` — machine key (submit_task, approve_task_review, return_task_review, etc.)
- `by_user` — user ID of who performed the action
- `occurred_at` — ISO 8601 timestamp
- `status_changed_from` / `status_changed_to` — status transition if any

### Step 4 — Pull Review Notes and Comments

This step is critical and has important technical nuances. Review notes and comments capture
the *substance* of the review — not just that someone clicked "approve", but that they
actually asked questions and got answers. Auditors will scrutinize this closely.

#### Entity-1 key requirement for rec and flux tasks

For reconciliation and flux tasks, the `key_id` from `list_tasks` includes an entity
dimension — the format is typically `api_xxx/ENTITY_NUMBER/ACCOUNT_NUMBER` or
`grp_xxx/ROW_NUMBER`. The `get_task_comments` API **only returns comments when using the
entity-1 variant of the key_id**. Other entity variants (e.g., `/3/`, `/4/`, `/6/`) will
return empty results even if comments exist.

To handle this correctly for reconciliation tasks:
1. Parse each key_id to extract the account number (last segment after the final `/`)
2. Rebuild the key_id with entity 1: `{prefix}/1/{account_number}`
3. Deduplicate — multiple entity variants of the same account share the same comments
4. Query using these entity-1 keys

For checklist and journal_entry tasks, this is not an issue — their key_ids are simple
`tsk_xxx` format with `key_type="custom"` and `report_id="checklist"`.

For flux tasks, use the key_id as-is from the listing, but be aware that comments are
stored at the entity-1 level. If a flux key_id contains an entity segment, convert it to
entity 1 just as with reconciliation tasks.

#### API call structure

Call `get_task_comments` for each task with:
- `task_key`: `{id: <key_id>, type: <key_type>, report_id: <report_id>}`
- `period_id`: the selected period ID

The response includes two arrays:
- `comments` — individual comment objects with `id`, `body`/`content` (may contain HTML),
  `created_at`, `created_by`/`user_id`, and optionally `review_note_id`
- `review_notes` — review note metadata with `id`, `comment_id` (links to a comment),
  `assignee_id`, `status` ("resolved" or "open"), `due_date`, `created_at`, `created_by`

Review notes and comments are linked: a review note's `comment_id` points to the comment
that contains the actual text, and a comment's `review_note_id` points back to the review
note metadata. To correctly identify which comments are review notes, cross-reference both
arrays using these linking fields.

#### Batching strategy

Since this is one API call per task and there may be 1000+ tasks across all four types,
use subagents to parallelize. Split the tasks into batches of ~100 and launch each batch
as a separate subagent. Give each subagent explicit, complete lists of task keys to query
(not just "query all tasks" — agents work better with specific task IDs).

Save each batch's results to a separate JSON file, then combine them at the end.
Deduplicate by (task_name, comment_body, created_at) to avoid double-counting if the
same comment appears under multiple entity variants.

### Step 5 — Build the Excel Workbook

Run the bundled `scripts/build_workbook.py` script, which takes JSON input files and
produces a professional Excel workbook using openpyxl.

```bash
python3 scripts/build_workbook.py \
  --workspace-name "<WORKSPACE>" \
  --period-slug "<PERIOD>" \
  --period-status "<STATUS>" \
  --rec-tasks rec_tasks.json \
  --checklist-tasks checklist_tasks.json \
  --events all_events.json \
  --comments all_comments.json \
  --users user_map.json \
  --output "<WORKSPACE>_<PERIOD>_Audit_Evidence.xlsx"
```

The workbook has five sheets:

#### Sheet 1: "Reconciliation Tasks"
All balance-sheet account reconciliations with columns:
Account Name | Preparer | Prep Status | Prep Due | Reviewer | Review Status | Review Due | Link

- Resolve user IDs to names using the workspace context
- Color-code status cells: green fill for COMPLETE, orange fill for PENDING
- Include auto-filters and freeze the header row
- Add a title row with workspace name, period, and generation date

#### Sheet 2: "Checklist Tasks"
All checklist items (custom + journal_entry tasks combined) with columns:
Task Name | Preparer | Prep Status | Prep Due | Reviewer | Review Status | Review Due

#### Sheet 3: "Activity Log"
Every event (excluding system_create_task for cleanliness) sorted chronologically:
Date/Time (UTC) | Event | Action By | Status Change | Task ID | Via

- Format timestamps as YYYY-MM-DD HH:MM:SS
- Green fill for approval rows, yellow fill for rejection/return rows
- Include auto-filters and freeze the header row
- This is the core evidence sheet — it shows the complete audit trail

#### Sheet 4: "Review Notes & Comments"
All comments and review notes across every task type, sorted by task name then date:
Task Name | Task Type | Comment/Note | Author | Date | Is Review Note | Resolved | Resolved By | Resolved Date

- Task Type should distinguish "Reconciliation", "Checklist", "Flux Analysis", and
  "Journal Entry" so auditors can filter by category
- Strip HTML tags from the comment body
- Highlight unresolved review notes with a yellow fill (open items auditors will ask about)
- Resolved review notes get a green fill
- General comments (non-review-notes) get no special fill
- Include auto-filters so auditors can filter to just review notes, just unresolved, etc.

#### Sheet 5: "Summary"
Aggregate statistics:
- Task status counts (prep complete, review complete, pending, etc.)
- Event type breakdown (approvals, submissions, rejections, reassignments)
- Activity by user (who did how many actions)
- Review notes summary: total notes, resolved count, unresolved count
- Comments summary: total comments across all tasks

#### Formatting standards
- Font: Arial, size 9-10 for data, 14 for titles
- Header rows: white bold text on dark fill (blue for recs, orange for checklist,
  green for activity log, purple for comments, gold for summary)
- Thin gray borders on all data cells
- Column widths set appropriately (55 for names, 25 for people, 12-14 for dates/statuses)
- Sheet tab colors matching the header color scheme

### Step 6 — Save and Share

Save the workbook to the outputs folder with a descriptive name:
`<WORKSPACE>_<PERIOD>_Audit_Evidence.xlsx`

Example: `WHOOP_Dec2025_Audit_Evidence.xlsx`

Provide the user a download link and a brief summary of what's in the file (task counts,
event counts, comment counts, period covered). Keep the summary concise.

## Comments JSON format

The combined comments file fed to build_workbook.py should be a JSON array where each
entry has these fields:

```json
{
  "task_name": "Reconcile Prepaid Expenses (140000)",
  "task_type": "Reconciliation",
  "body": "can you also include the prepaid pending bills accrual listing...",
  "created_at": "2026-01-15T14:30:00.000Z",
  "user_id": "usr_xxx",
  "author": "Jack Eisele",
  "review_note": true,
  "resolved": true,
  "resolved_by": "Christopher Freitas",
  "resolved_at": "2026-01-16T10:00:00.000Z"
}
```

The `author` field should already be resolved to a display name (not a user ID). The
`task_type` field should be one of: "Reconciliation", "Checklist", "Flux Analysis", or
"Journal Entry".

## Performance

Fan out per task (batches of ~50), use the bundled parser scripts, and checkpoint per task. Materiality is auditor-driven, not skill-driven. See `references/performance.md` for the full pattern.

## Edge Cases

- **Large workspaces (500+ tasks per type):** Batch API calls in groups of 50 for events,
  100 per subagent for comments. Parse large result files from disk rather than trying to
  hold everything in memory at once.
- **Entity variants in key_ids:** The same account may appear under multiple entities (e.g.,
  `api_xxx/1/351`, `api_xxx/3/351`, `api_xxx/4/351`). Comments only live on entity 1.
  Deduplicate by account number before querying comments to avoid redundant API calls.
- **Tasks with no events:** Some tasks (especially auto-submitted ones) may have very few
  events. Include them in the task listing sheets even if the activity log has no entries.
- **Missing reviewers:** Not all tasks have reviewers assigned. Leave reviewer columns blank
  rather than showing "None" or an ID.
- **Multiple entities in one workspace:** The reconciliation module may have tasks across
  different entities. Include all of them — the auto-filters let auditors slice by entity.
- **Period still open vs closed:** This skill works for both open and closed periods.
  Mention the period status in the title row so auditors know if the close is still in
  progress.
- **Tasks with no comments:** Most tasks won't have comments or review notes. Only include
  rows in the "Review Notes & Comments" sheet for tasks that actually have content.
- **HTML in comment bodies:** Comment text from Numeric may contain HTML formatting tags
  (`<p>`, `<br>`, `<a>`, `<strong>`, etc.). Strip all HTML to plain text for the
  spreadsheet. Preserve line breaks where `<br>` or `</p>` appear.
- **Review note linking:** The API returns `comments` and `review_notes` as separate arrays.
  A review note's `comment_id` points to the comment with the actual body text. A comment's
  `review_note_id` points to the review note with status/assignee metadata. Cross-reference
  both to correctly identify which comments are formal review notes vs. general comments.
- **Flux tasks with path-type keys:** Flux tasks may use `key_type="path"` with key_ids
  like `grp_xxx/NNN`. These work directly with `get_task_comments` — just pass them as-is.
