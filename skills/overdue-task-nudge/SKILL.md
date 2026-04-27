---
name: overdue-task-nudge
description: >
  Sends Slack reminders for overdue or upcoming-due Numeric tasks. Reads preferences from each task's own description (## Reminder preferences section), falls back to defaults if not found, and writes them back after each run. Determines recipients from task descriptions and assignees. Logs each reminder as a task comment to prevent duplicate nudges. Trigger when the user says: remind assignees, send task nudges, chase outstanding recs, ping people on overdue tasks, send close reminders, nudge people on late tasks, remind everyone about their tasks, send overdue nudges, who hasn't finished their tasks, or run a reminder sweep in Numeric.
---

# Overdue Task Nudge

Sweeps a Numeric workspace for overdue tasks that are unblocked, determines who to notify from each task's description and assignees, sends Slack DMs, and logs the action as a task comment to prevent duplicate messages within the cooldown window.

---

## Step 0: Establish default preferences

Preferences are per-task — each task's description may contain a `## Reminder preferences` section that overrides these defaults for that specific task. Defaults are applied to any task that doesn't have that section.

```
remind_days_before_due: 0        (days before due date to start reminding; 0 = on/after due date only)
reminder_cooldown_hours: 24      (minimum hours between reminders for this task)
channel: slack                   (slack = Slack DM; email = uses email MCP if available)
```

For any task that runs on defaults, append this block to its description at the end of the run so the team can see and tune it next time.

If the user asks to change a default mid-conversation, update it for the current run and note it in the summary.

---

## Step 1: Discover scope

1. Ask the user: **"Run reminders for all pending tasks, or specific tasks you'd like to name?"**
   - If specific tasks, collect the names or IDs and filter to those in Step 2.
   - If all tasks, proceed without a filter.
2. Call `list_workspaces` — if the user hasn't specified a workspace, show the list and ask which one to run against.
3. Call `set_workspace` with the chosen workspace ID.
4. Call `get_workspace_context` — extract:
   - The **current open period** (most recent period with an open/active status)
   - The **workspace user roster** (id, name, email) — used later to resolve recipient names

---

## Step 2: Fetch pending tasks and read per-task preferences

Call `list_tasks` with:
- `period_id`: current period from Step 1
- `status`: `PENDING`
- `include_description`: `true`
- If the user named specific tasks, filter results to those after fetching

For each task, check its description for a `## Reminder preferences` section. If found, parse those values as the preferences for that task. If not found, use the session defaults from Step 0.

---

## Step 3: Filter to tasks that need a reminder

**3a. Apply the due date threshold**

Using each task's own `remind_days_before_due` preference:
```
reminder_threshold = today + remind_days_before_due days
```
Keep tasks where `due_date <= reminder_threshold`.

Tasks with no due date: skip and note in the summary under "Skipped – no due date."

**3b. Check for unresolved dependencies**

Scan each candidate task's description for blocking references — lines like `Blocked by: [task name]`, `Depends on: [task name]`, or `Waiting on: [task name]`. If a referenced task is still PENDING, skip the reminder and note it under "Skipped – blocked by incomplete dependency." No point nudging someone on a task they can't complete yet.

---

## Step 4: Check cooldown via task comments

For each remaining candidate, call `get_task_comments`. If any comment contains `🔔 Numeric reminder sent` and was posted within the last `reminder_cooldown_hours` hours → skip. This prevents repeat messages when the skill is run multiple times in a day.

---

## Step 5: Determine recipients and resolve Slack handles

For each eligible task, build a recipient list from two sources:

**From the task description** (higher priority — represents intentional routing):
- `@Name` mentions, email addresses, or lines like `Notify: Jane, Bob`

Match parsed names/emails against the workspace user roster to get user IDs, then call `slack_search_users` to get their Slack handle.

**From assignees** (fallback if description yields no recipients):
- Include the preparer and reviewer if present, then resolve their Slack handles the same way.

Deduplicate. If no Slack match is found for someone, note them in the summary and continue. Group all eligible tasks by recipient — one DM per person, not per task.

---

## Step 6: Build and send messages

Compose one message per recipient. Tone: warm and helpful — a nudge, not an escalation.

```
Hey [First Name] 👋 — you have [N] task(s) in Numeric that need attention:

• *[Task Name]* — due [due_date] ([X days overdue / due today / due in X days])
  [Task URL]
  📝 Review note: "[note text]"   ← only if open review notes exist on this task

Let me know if you have questions!
```

If the channel preference is `email`, check whether an email MCP tool is available (look for tools named `email`, `gmail`, `send_email`, `draft_email`, or similar). If found, use it to send to the recipient's email from the workspace roster. If no email tool is available, tell the user, log what would have been sent, and skip.

---

## Step 7: Log the reminder on each task

After sending, call `add_task_comment` on every task included in a message:

```
🔔 Numeric reminder sent to [Recipient Name] via [channel] on [YYYY-MM-DD HH:MM local time]
```

This is what Step 4 checks on future runs to enforce the cooldown.

---

## Step 8: Sync preferences back to each task description

For every task processed, update its description using `edit_task` to reflect the preferences that were actually used:

- **No `## Reminder preferences` section existed** → append the defaults block
- **Section existed and preferences changed** (e.g. user updated a default mid-run) → overwrite just that section with the new values
- **Section existed and nothing changed** → leave the description untouched

This keeps each task's description in sync with what was used, so the next run picks up the right values.

---

## Step 9: Summary to user

```
Reminder sweep complete — [date]

✅ Messaged [N] people across [M] tasks
  • Jane Smith — Cash Reconciliation, AP Subledger, Payroll Accrual
  • Bob Chen — Fixed Assets

⏸  Skipped – already reminded within cooldown: [task names]
🔒  Skipped – blocked by incomplete dependency: [task names + blocker]
⏭  Skipped – no due date: [task names]
❌  Could not resolve Slack handle: [names]
```
