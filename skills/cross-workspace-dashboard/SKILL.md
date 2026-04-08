---
name: cross-workspace-dashboard
description: >
  Cross-workspace executive close dashboard — rolls up multiple Numeric workspaces (entities) into a single portfolio-level HTML dashboard with companion Excel workbook. Use only when the user explicitly needs a multi-entity or portfolio view. Trigger for: "cross-workspace close dashboard", "portfolio close", "multi-entity close", "multi-workspace close", "close across all entities", "close status across entities", "which entities are behind", "who's overloaded across the portfolio", "executive close view", "CFO dashboard across entities", "controller dashboard", "portfolio close status", "compare entities", "which workspaces are behind", "show me all entities". Do NOT trigger for single-workspace close questions — use close-pulse for those. This skill is for users managing multiple entities who need a comparative, rolled-up view.
---

# Cross-Workspace Close Dashboard

Build a dark-themed executive HTML dashboard and companion Excel workbook that
rolls up close progress, assignee workload, overdue tasks, reviewer bottlenecks,
and prioritized action items **across multiple Numeric workspaces** for a
selected close period.

This skill is for portfolio-level visibility — a CFO, controller, or close
manager who oversees multiple entities and needs a single comparative view of
where every entity stands.

> **Use this skill when:** The user manages or wants to view 2+ workspaces
> (entities) at once, or is asking about portfolio-level close health.
>
> **Use `close-pulse` instead when:** The user wants a deep operational view
> of a *single* workspace — task-level triage, materiality flags, dependency
> chains, or close pace for one entity.

The cross-workspace dashboard is deliberately aggregated and comparative —
it answers "which entities are behind?" and "who's overloaded across the
portfolio?" rather than drilling into individual task details.

## Outputs

1. **HTML Dashboard** — A Geckoboard-style dark-themed visual dashboard with:
   - KPI cards (completion %, overdue count, active entities, rec status, JE status)
   - Entity completion bars ranked by progress
   - Donut chart showing overall portfolio progress
   - Task mix breakdown (recs, JEs, custom, flux)
   - Preparer workload bars with completion %
   - Overdue task table with days-late calculation
   - 8–10 prioritized action items with owner and deadline
   - Deadline timeline (overdue → next 3 days → rec wave)
   - Reviewer concentration risk analysis

2. **Excel Workbook** — Granular detail behind the dashboard:
   - Executive Summary tab with KPIs and entity/preparer tables
   - Action Items tab with prioritized list
   - Overdue Tasks tab
   - Entity Status tab
   - Per-entity detail tabs (one per active workspace)

## Workflow

### Step 1: Select workspaces

Call `list_workspaces` to get all available workspaces. Present them to the
user using `AskUserQuestion` with `multiSelect: true` so they can pick which
workspaces to include in the dashboard.

If the user has already specified workspaces (by name, by keyword like
"all Connect workspaces", or by workspace ID), match against the list and
proceed. For keyword matching (e.g., "all workspaces with Connect in the
name"), filter the workspace list and confirm the matches with the user.

If the keyword filter returns zero matches, tell the user which workspaces
are available and ask them to clarify. Don't silently fall back to all
workspaces — the user chose a filter for a reason.

### Step 2: Select the close period

Ask the user which close period to analyze. Common options:
- A specific month like "March 2026"
- "Most recent" or "current close"

You'll resolve this to actual period IDs per-workspace in Step 3. Different
workspaces may use different period slug formats (e.g., "mar-2026" vs
"2026-03"), so match flexibly.

### Step 3: Pull data from all workspaces

This is the core data collection step. Launch parallel subagents — one per
workspace (or batch 3–5 per agent if there are many) — to pull data
simultaneously.

**For each workspace, the agent must do ALL of the following in order:**

```
1. set_workspace(workspace_id)
2. get_workspace_context → extract:
   - Period list (find the target period by matching month/year)
   - User list (name, ID, active status)
   - Entity list
3. list_tasks(period_id) — NO filters, get everything
4. IF step 3 returns 0 tasks, the workspace may organize tasks by type.
   Try each type individually:
   - list_tasks(period_id, task_type="rec_prepare_account")
   - list_tasks(period_id, task_type="custom")
   - list_tasks(period_id, task_type="journal_entry")
   - list_tasks(period_id, task_type="flux")
   Combine all results.
5. list_tasks(period_id, status="COMPLETE")
6. list_tasks(period_id, status="PENDING")
```

This fallback in step 4 is important — some workspaces return 0 on an
unfiltered pull but have hundreds of tasks when queried by type. Always try
the type-specific queries if the unfiltered pull is empty.

**What to collect per workspace:**
- Workspace name (confirmed by the API, not assumed from the ID)
- Period ID and status (open/closed)
- Total task count, by status (COMPLETE, PENDING, SKIPPED, IMMATERIAL)
- Task count by type (rec_prepare_account, custom, journal_entry, flux)
- Per-task detail: name, type, prep_assignee, prep_status, prep_due,
  review_assignee, review_status, review_due
- Assignee breakdown: per prep_assignee → total, complete, pending
- Assignee breakdown: per review_assignee → total, complete, pending
- Overdue tasks: any task where prep_due < today and prep_status = PENDING
- Bank/cash related tasks (name contains "bank", "cash", or "reconcil")

**Workspace routing caveat:** Numeric's set_workspace can sometimes route to
a different workspace than expected. Always verify the workspace name returned
by the API matches what you intended. If it doesn't match, note the
discrepancy in the output rather than silently using wrong data.

### Step 4: Aggregate the data

Once all agents return, combine into a portfolio-level view:

```
Portfolio totals:
  total_tasks = sum across all workspaces
  complete_tasks = sum of COMPLETE
  pending_tasks = sum of PENDING
  completion_pct = complete / total
  overdue_count = count of tasks past due date and still PENDING

Per-entity summary:
  For each workspace: name, total, complete, pending, skipped, completion %

Cross-entity preparer rollup:
  Group by prep_assignee name across all workspaces
  Sum their total/complete/pending
  Calculate per-person completion %
  Rank by volume (total tasks)

Reviewer concentration:
  Group by review_assignee across all workspaces
  Flag anyone reviewing > 25% of portfolio tasks

Task type mix:
  rec_prepare_account total, custom total, journal_entry total, flux total

Overdue list:
  All tasks past due, sorted by days late descending
  Include: task name, workspace, prep_assignee, due_date, days_late

Action items (generate 8–10):
  Priority-ranked list based on:
  1. Overdue tasks that block other work (IC invoices, bank recs)
  2. Preparers with 0% completion and large task counts
  3. Reviewer single-points-of-failure
  4. Entities at 0% completion
  5. Upcoming deadline waves
  6. Reconciliation run-rate math (recs remaining / days to deadline)
```

### Step 5: Build the HTML dashboard

Create a single-file HTML dashboard matching the Numeric design language below.
Save to the outputs folder.

#### Design System

Match Numeric's visual style — clean light background, violet/purple brand
palette, Inter font. This should feel like a natural extension of the Numeric
app, not a generic dashboard.

**Color palette:**
- Page background: `#f7f7fb` (very light lavender-white)
- Card background: `#ffffff`
- Card border: `#e8ecef` (cool gray — matches Numeric's `rgb(232,236,239)`)
- Card shadow: `0 1px 4px rgba(31,0,69,0.06)` (subtle, purple-tinted)
- Border radius: `12px` for cards, `4px` for pills/controls

**Brand colors (Numeric):**
- Primary violet: `#7036ff` — buttons, links, progress fills, KPI accents
- Deep navy-purple: `#1f0045` — page header bar, high-contrast text
- Lavender surface: `#eeeeF5` — active/selected badge backgrounds
- Lavender mid: `#b1a6ce` — secondary accents, muted fills

**Text:**
- Primary: `#1f0045` (dark navy-purple)
- Secondary: `#4d4d5b` (matches Numeric's `rgb(77,77,91)`)
- Muted/label: `#778ca2`

**Status colors:**
- Complete (green): `#12b76a` / light bg `#ecfdf5`
- Pending/warning (amber): `#f79009` / light bg `#fffaeb`
- Overdue (red): `#e53935` / light bg `#fef2f2`
- Skipped (gray): `#9e9e9e` / light bg `#f5f5f5`
- In-progress (violet): `#7036ff` / light bg `#f0ebff`

**Typography:** Inter font (from Google Fonts or system). KPI values at
36px/700. Section labels at 11px/600 uppercase with 0.8px letter-spacing in
`#778ca2`. Body text at 13–14px.

**Page header:** Full-width bar in `#1f0045` with white Numeric-logo wordmark
(use text "Numeric" in white with the ● logo character or SVG inline), period
label, and generated timestamp.

**KPI cards:** White card with `#e8ecef` border, colored left border (4px)
using the relevant status color. Label in muted uppercase, value in `#1f0045`
at 32px/700, subtitle line in `#778ca2`.

**Progress bars:** 8px height, `#eeeeF5` track, `#7036ff` fill for completion.
Color-code the fill: green `#12b76a` if >80%, violet `#7036ff` if 40–80%,
amber `#f79009` if 10–40%, red `#e53935` if <10%.

**Donut chart:** SVG-based, 140px diameter. Violet for complete, `#e8ecef` for
pending, `#9e9e9e` for skipped.

**Badges/pills:** `border-radius: 4px`, 11–12px font, `font-weight: 600`.
Use colored text on light tinted backgrounds from the status color set above.

**Tables:** No outer border. Row dividers at `#e8ecef`. Header row background
`#f7f7fb`, header text in uppercase 11px muted. Alternating rows white/`#f7f7fb`.

**Action items:** Left-colored border (4px) per priority level. Priority badge
is a pill: red for critical, amber for high, violet for medium.

**Responsive:** Grid collapses to single column at 960px.

#### Dashboard Layout

```
Row 1: [KPI] [KPI] [KPI] [KPI] [KPI]
Row 2: [Entity Bars (2col)] [Donut + Task Mix]
Row 3: [Preparer Workload] [Overdue Table]
Row 4: [Action Items (full width)]
Row 5: [Deadline Timeline] [Reviewer Risk]
Footer: Generated date + workspace count
```

### Step 6: Build the Excel workbook

Use openpyxl. Follow the xlsx skill conventions (read the xlsx SKILL.md for
formatting standards). Use the same dark color scheme for cell fills where
appropriate (dark backgrounds look good in Excel too).

**Tabs to create:**
1. Executive Summary — KPIs, entity table, preparer table
2. Action Items — Priority-ranked with detail columns
3. Overdue Tasks — Full list with days-late
4. Entity Status — All workspaces with task counts and status
5. One tab per active workspace — Assignee breakdown and task type mix

After building, recalculate with `scripts/recalc.py` if formulas are used.

### Step 7: Deliver

Save both files to the outputs folder:
- `Close_Dashboard_{period}.html`
- `Close_Dashboard_Detail_{period}.xlsx`

Present both files to the user with computer:// links and a brief summary:
portfolio completion %, how many entities active, top 3 action items.

## Tips for Generating Good Action Items

The action items are the most valuable part of the dashboard. They should be
specific, actionable, and tied to a named person. Generic advice like
"accelerate the close" is useless. Good action items follow this pattern:

**Pattern:** [Person] has [specific problem] at [entity] — [what to do]

**Examples of good action items:**
- "Querien Diaz has 8 overdue IC invoices at Operating Partners — clear these
  immediately as they block IC elimination across the portfolio"
- "Rene Delgado owns 62 tasks across 2 entities and hasn't started — engage
  by tomorrow or redistribute to Oscar and Querien"
- "Oscar Cruz is sole reviewer for 159 tasks across 2 entities — add a backup
  reviewer (Juan Alameda) to prevent single-point-of-failure"

**Examples of bad action items:**
- "Speed up the close process"
- "Review overdue tasks"
- "Ensure reconciliations are completed on time"

Always include the math: "61 recs, 13 days left = 5/day needed" is much more
useful than "reconciliations are behind."
