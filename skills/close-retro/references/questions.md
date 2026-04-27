# Close Retro Question Bank

Questions the close retro can answer, organized by theme. Each question lists which data sources are needed and whether the current Numeric MCP data can answer it.

## How to use this file

When building the digest, scan this list and attempt to answer every question marked `answerable: yes`. Skip questions where the data is missing or insufficient. Group your answers by theme in the output.

---

## Pace & Timing

### Are we getting faster or slower at closing?
- **answerable:** yes (with prior period)
- **data:** Compare close cycle time (first submit_task to last submit_task) across periods
- **metric:** Close cycle time delta

### Is work getting done steadily or crammed at the end?
- **answerable:** yes
- **data:** submit_task events grouped by calendar day
- **metric:** Back-loading score — % of completions in final 25% of close window. Above 50% = back-loaded.

### How long does a typical task take from assignment to completion?
- **answerable:** yes
- **data:** assign_task → submit_task timestamps per task
- **metric:** Median turnaround days (overall, prep, review)

### How quickly do people start working after being assigned?
- **answerable:** yes
- **data:** First assign_task → first non-assignment event per task
- **metric:** First-touch latency (median, P90, % dormant)

### Which tasks took the longest?
- **answerable:** yes
- **data:** Turnaround days per task, sorted descending
- **metric:** Top 5 slowest tasks with assignee and type

---

## Review Quality

### How often do tasks get sent back for rework?
- **answerable:** yes
- **data:** unsubmit_task event count per task
- **metric:** Total reopens, tasks with 2+ reopens (high-friction)

### How long does a rework cycle take?
- **answerable:** yes
- **data:** unsubmit_task → next submit_task timestamp
- **metric:** Median reopen cycle days

### Which tasks had the most back-and-forth?
- **answerable:** yes
- **data:** Tasks sorted by unsubmit_task count descending
- **metric:** High-friction task list (2+ reopens)

### Are reviews keeping up with prep work?
- **answerable:** yes
- **data:** Tasks where prep is COMPLETE vs. review has started
- **metric:** Handoff rate — % of prep-complete tasks that moved to review

### Is anyone reviewing their own work?
- **answerable:** yes
- **data:** Tasks where prep_assignee == review_assignee
- **metric:** Self-review count

---

## Workload & Balance

### Is work spread evenly or concentrated on a few people?
- **answerable:** yes
- **data:** Total tasks (prep + review) per assignee
- **metric:** Top-3 and top-5 share of total workload

### Who has the most on their plate?
- **answerable:** yes
- **data:** Per-user task counts
- **metric:** Assignee leaderboard sorted by total tasks

### Who's finishing fastest? Who's slowest?
- **answerable:** yes
- **data:** Per-user median turnaround days
- **metric:** Fastest and slowest median turnaround with names

### Are some people causing more rework than others?
- **answerable:** yes
- **data:** Per-user reopens caused (as reviewer) and reopens received (as preparer)
- **metric:** Reopens caused/received per person

### Does anyone have tasks they haven't touched?
- **answerable:** yes
- **data:** Tasks assigned to user with zero non-assignment events
- **metric:** Dormant task count per person

---

## Coverage & Setup

### Are tasks assigned to someone?
- **answerable:** yes
- **data:** Tasks with blank prep_assignee or review_assignee
- **metric:** Unassigned prep count, unassigned review count

### Do tasks have due dates?
- **answerable:** yes
- **data:** Tasks with no prep_due and no review_due
- **metric:** % of tasks without any due date

### Were tasks reassigned a lot?
- **answerable:** yes
- **data:** assign_task events with different user IDs on same task
- **metric:** % of tasks reassigned, median assignment changes

---

## Late Work

### How many tasks missed their due date?
- **answerable:** yes (partial — need submit_task timestamp vs. due date)
- **data:** submit_task occurred_at vs. prep_due/review_due from task list
- **metric:** Late task count, % late, average days late

### Who was late most often?
- **answerable:** yes
- **data:** Late tasks grouped by assignee
- **metric:** Per-person late count and %

### Were due dates moved to hide lateness?
- **answerable:** yes
- **data:** edit_target_date events per task
- **metric:** Due date drift — % of tasks with date changes, tasks with 3+ changes

---

## Not Answerable from Numeric Data Alone

These questions would need data from other systems (Slack, Gong, calendar, etc.). The skill should not attempt to answer these but could note them as areas for future investigation if the user is interested.

- **Communication:** Was the close kickoff communicated clearly? Were blockers escalated quickly?
- **External dependencies:** Did we wait on external parties (auditors, banks, vendors)?
- **Process:** Are there tasks that should be automated or eliminated?
- **Training:** Does anyone need help with specific task types?
- **Tool adoption:** Are people using Numeric effectively or working around it?
- **Satisfaction:** How did the team feel about this close?
