# Close Pulse — Lens Implementations

## Lens 1: By the Numbers (Materiality)

Surfaces reconciliation accounts where the GL balance and reconciled balance diverge beyond a materiality threshold. The core data source is the recon report, which compares each account's GL Balance against its Rec. Balance (the sum of reconciling items entered by the preparer). A variance means the account isn't fully reconciled yet — either work hasn't started, or there are unexplained differences.

### Steps

1. Ask the user for their materiality threshold:
   - Absolute: e.g., "$5,000" — flag any variance above this amount
   - Percentage: e.g., "10%" — flag any variance above this percentage
   - Both: flag accounts exceeding either threshold
   - If the user doesn't specify, suggest $5K and 10% as starting defaults

2. Find the recon report:
   - Call `list_tasks` with `task_type: "rec_prepare_account"` and the target `period_id` to confirm recon tasks exist
   - The `report_id` on those tasks identifies the recon report (typically a single report ID like `rep_...`)
   - If no `rec_prepare_account` tasks are found, the workspace may not have a recon module configured — inform the user and fall back to flux variance analysis as a secondary option

3. Pull recon report data:
   - Call `get_report_data` with the recon report's `report_id` as the `configuration_id` and the target `period_id`
   - The response is TSV with these key columns: Account, Entity, GL Balance, Rec. Balance, Rec. Items, Variance ($), Variance (%)
   - Parse each row to extract the GL Balance vs. Rec. Balance comparison
   - Note: rows with empty Variance ($) and Variance (%) mean no reconciliation work has been entered yet — these are unstarted accounts, not zero-variance accounts. Flag them separately.

4. Filter and categorize:
   - **Material variances**: accounts where abs(Variance $) exceeds the threshold or abs(Variance %) exceeds the percentage threshold
   - **Unreconciled accounts**: accounts with a GL Balance but no Rec. Balance populated at all — these haven't been touched yet and may represent the biggest risk
   - **Clean accounts**: accounts where Variance = $0 or within threshold — no action needed

5. For material variances, cross-reference with task status:
   - Match each flagged account back to its `rec_prepare_account` task from the task list
   - Show whether the preparer has marked it COMPLETE (variance may be expected/explained) or PENDING (needs attention)
   - If prep is COMPLETE but variance is material, the reviewer should focus there

6. Output a prioritized shortlist:
   - Account code and name
   - Entity (if multi-entity)
   - GL Balance and Rec. Balance
   - Variance $ and %
   - Prep status (COMPLETE / PENDING / unassigned)
   - Sort by absolute variance descending

7. Optionally drill into drivers:
   - For the top flagged accounts, call `query_transaction_lines` with the account's key, report_id, and the period's date range
   - Identify the top 3-5 transactions by absolute amount contributing to the unexplained variance

### Filtering options
- By account category (Asset, Liability, Equity, Revenue, Expense) using the Type/Subtype columns from the recon report
- By entity (for multi-entity workspaces, filter to a single entity or compare across entities)
- By variance direction (positive = rec balance exceeds GL, negative = GL exceeds rec balance)
- By GL code pattern (e.g., "1xxx" for assets only, "2xxx" for liabilities)

---

## Lens 2: By the Dates (Overdue / Urgency)

Surfaces tasks by urgency bucket and identifies bottleneck assignees.

### Steps

1. Call `list_tasks` for the target `period_id` — pull across all reports or filter to specific `report_ids` if the user specifies a module

2. Parse the task data and categorize into urgency buckets based on due dates vs. today:
   - **Overdue**: due date < today AND status ≠ COMPLETE
   - **Due today**: due date = today AND status ≠ COMPLETE
   - **Due this week**: due date within next 5 business days (use holidays from `get_workspace_context`)
   - **Upcoming**: due date > this week

3. Identify bottleneck assignees:
   - Count overdue items per assignee
   - Rank by count descending
   - "Sarah has 12 overdue tasks, Mike has 8, Lisa has 3"

4. Format as urgency digest:
   ```
   🔴 Overdue (15 tasks)
      Sarah Chen — 8 tasks (oldest: 5 days overdue)
      Mike Park — 5 tasks (oldest: 3 days overdue)
      Lisa Wang — 2 tasks (oldest: 1 day overdue)

   🟡 Due Today (4 tasks)
      ...

   🟢 Due This Week (22 tasks)
      ...
   ```

5. **Reminder action** (only if user explicitly requests):
   - For each overdue task, call `add_task_comment` with a reminder message and @mention of the assignee
   - Confirm before executing: "I'll post reminders on 15 overdue tasks mentioning the assignees. Proceed?"
   - Can suggest chaining with the `schedule` skill for daily automated nudges

---

## Lens 3: By the Progress (Close Status)

Computes completion stats per report and per assignee.

### Steps

1. Call `list_tasks` for the target `period_id` across all reports (or filtered to specific ones)

2. Compute per-report stats:
   - Total tasks
   - Completed (status = COMPLETE)
   - In progress (status = PENDING with at least one event/comment indicating work started — or use prep_status if available)
   - Not started (status = PENDING with no activity)
   - Skipped / Immaterial
   - % Complete = completed / (total - skipped)

3. Compute per-assignee stats:
   - Same breakdown but grouped by assignee
   - Flag assignees with < 50% completion if the close is > 50% through its timeline

4. Format as digest:
   ```
   Close Progress — March 2026

   Overall: 67% complete (142/212 tasks)

   By Report:
   • MoM IS Flux: 85% (34/40)
   • BS Recon: 45% (18/40) ← behind
   • Close Checklist: 72% (90/125)

   By Assignee:
   • Sarah Chen: 90% (45/50) ✓
   • Mike Park: 55% (22/40) ← needs attention
   • Lisa Wang: 70% (35/50)
   ```

---

## Lens 4: By the Pace (Day-by-Day Trending)

Compares this close's completion trajectory against prior periods.

### Steps

1. For the current period, call `list_tasks` and use `get_task_events` to get completion timestamps for each task. Group completions by business day.

2. Build a cumulative completion curve: for each business day since the period opened, how many tasks were complete?

3. For comparison periods (1-3 prior periods):
   - Call `list_tasks` for each prior `period_id`
   - Call `get_task_events` to get historical completion timestamps
   - Build the same cumulative curve

4. Compare:
   - "Day 5 of close: 45% complete this month vs. 52% at same point last month"
   - Flag if current pace is behind the prior period's pace by more than 10 percentage points

5. Compute close duration metrics:
   - Mean and median days to fully complete (across last 3-6 periods)
   - Current period's projected completion date based on current pace
   - Trend: "Close duration has increased from 8 days to 11 days over the last 3 months"

6. Identify pace laggards:
   - Which assignees are behind their own historical pace
   - Which specific days had lower-than-expected throughput

Use `get_workspace_context` for holiday calendars to correctly count business days.

---

## Lens 5: By Dependencies

Maps task dependencies and surfaces the critical path.

### Steps

1. Call `list_tasks` for the target period across all reports

2. Identify dependency relationships:
   - Tasks that reference other tasks (via description or linked tasks if available in the data)
   - Natural ordering: preparer must complete before reviewer can act (sequential workflow within a task)
   - Cross-report dependencies: e.g., "Journal entries must be posted before flux review"

3. Build a dependency graph:
   - For each incomplete task, identify what it's waiting on
   - Identify tasks that have no incomplete predecessors (ready to work)
   - Identify tasks that are blocked because an upstream task is incomplete

4. Find the critical path:
   - The longest chain of dependent incomplete tasks
   - These are the tasks that, if delayed further, will delay the entire close
   - "Critical path: Bank rec (Mike, 2 days overdue) → Cash flux review (Sarah, blocked) → Cash reconciliation sign-off (Lisa, blocked)"

5. Flag issues:
   - Circular dependencies (A depends on B depends on A)
   - Orphaned tasks (no predecessors or successors — may be forgotten)
   - Blocked chains where the blocking task has no assignee

6. Output: dependency-aware task list showing blocked status and critical path highlighting

Note: Numeric's task model doesn't have explicit dependency fields, so dependencies are inferred from task structure (prep → review → second review within a task), report ordering conventions, and any references in task descriptions/comments. This lens is inherently heuristic — flag this to the user.
