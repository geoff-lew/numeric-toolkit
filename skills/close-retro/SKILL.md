---
name: close-retro
user-invocable: true
description: >
  Close retrospective — analyzes how a close period went using task completion data, event timelines, review cycles, and assignee workload from Numeric. Produces a plain-language Slack digest organized around diagnostic questions (pace, review quality, workload balance, setup gaps). Optionally produces an HTML dashboard. Works on closed or in-progress periods. Trigger when the user says: close retro, close retrospective, how did the close go, close debrief, post-close review, close analysis, what went well this close, close performance, close review, close recap, month-end retro, how's the close tracking, close cycle time, who was late, what took longest, close bottlenecks, pace of close review, or any request to evaluate or reflect on a close period's performance.
---

# Close Retrospective

Analyzes a Numeric close period and produces a plain-language Slack digest with diagnostic insights about pace, review quality, workload balance, and setup gaps. The digest is organized around questions a controller or manager would actually ask, not raw statistics.

An HTML dashboard is available on request but is not the default — the digest is the primary deliverable.

## Bundled resources

This skill ships with Python scripts that handle all data parsing and metric computation. Using these scripts is much faster than doing the work inline, because MCP responses are large and unwieldy to process in-context.

```
scripts/
├── parse_context.py   — workspace context → user_map.json + periods.json
├── parse_tasks.py     — list_tasks TSV → tasks.json with aggregates
├── parse_events.py    — get_task_events → merged events.json with user names resolved
├── compute_metrics.py — tasks.json + events.json → metrics.json
└── generate_digest.py — metrics.json → Slack-ready digest.md
references/
└── questions.md       — question bank mapping diagnostic questions to data sources
```

---

## Step 0: Discover scope

1. Call `list_workspaces`. If the user hasn't specified a workspace, show the list and ask.
2. Call `set_workspace` with the chosen workspace ID.
3. Call `get_workspace_context`. **The response will be large** (50K+ chars). It gets saved to a tool-result file. Parse it immediately with the bundled script:
   ```bash
   python3 <skill_path>/scripts/parse_context.py <context_result_file> <work_dir>
   ```
   This produces `user_map.json` (user ID → name mapping) and `periods.json` (all periods with dates and status).
4. Ask which period to retrospect. Default: most recently closed period. If no closed periods, offer the current open period and note the retro will reflect progress-to-date.

---

## Step 1: Pull and parse task data

Call `list_tasks` with:
- `period_id`: chosen period
- `include_description`: `false`

The response is TSV and will be large for real workspaces. Parse immediately:

```bash
python3 <skill_path>/scripts/parse_tasks.py <tasks_result_file> <work_dir>
```

The script parses all tasks in the period by default. An optional third argument can cap the count if needed (e.g. `500`), but the default is to process everything.

The script outputs `tasks.json` with: total count, status breakdown, task type breakdown, per-assignee counts, due date coverage, and the task array.

---

## Step 2: Pull event timelines

Events power the efficiency metrics (turnaround, reopens, first-touch, etc.). They must be pulled in batches because the API returns 500 on bulk calls.

**Batching strategy:** Group task `key_id` values from the parsed task list. Call `get_task_events` with `task_keys` set to ~15 keys per batch. Run 4–6 batches (covering 60–90 tasks) — this provides enough signal for the metrics without taking too long.

Each batch response gets saved to a tool-result file. After all batches complete, merge and parse:

```bash
python3 <skill_path>/scripts/parse_events.py <work_dir>/user_map.json <work_dir> <batch1.txt> <batch2.txt> ...
```

This resolves user IDs to names (using the user_map from Step 0) and outputs a single `events.json` sorted by timestamp.

**Important:** The `key_id` values passed to `task_keys` must match what the API expects. Use the `key_id` field from the parsed tasks, not the task name or URL.

---

## Step 3: Compute metrics

```bash
python3 <skill_path>/scripts/compute_metrics.py <work_dir>/tasks.json <work_dir>/events.json <period_start_date> <work_dir>
```

This computes all efficiency metrics and saves `metrics.json`. The metrics include:

- **Turnaround**: median/mean/P90 days from assignment to completion (overall, prep-only, review-only)
- **Handoff rate**: % of prep-complete tasks that moved to review
- **First-touch latency**: how quickly people start after assignment, % dormant
- **Reassignment churn**: % of tasks reassigned, median assignment changes
- **Reopen cycles**: total reopens, cycle time, high-friction tasks (2+ reopens)
- **Coverage**: unassigned tasks, missing due dates, self-review count
- **Workload concentration**: top-3/top-5 share of total tasks
- **Per-user**: tasks, completion rate, turnaround, reopens caused/received, dormant count

---

## Step 4: Generate the digest

```bash
python3 <skill_path>/scripts/generate_digest.py <work_dir>/metrics.json "<workspace_name>" "<period_name>" <output_dir>
```

This produces `digest.md` — a Slack-formatted summary organized around questions:

1. **Quick numbers** — KPI snapshot at the top (completion %, turnaround, handoff rate, reopens, coverage gaps, churn)
2. **How's the pace?** — first-touch latency, turnaround distribution
3. **Is the review process working?** — handoff rate, reopens, rework cycle time, self-review
4. **Is work spread evenly?** — concentration, most loaded person, fastest/slowest, dormant tasks
5. **Setup gaps** — unassigned tasks, missing due dates, high reassignment
6. **What went well / What to watch** — auto-derived from the data
7. **Suggested actions** — 1–3 concrete next steps

The digest uses plain language throughout. "Median turnaround" becomes "a typical task takes X days." Avoid statistical jargon (no Gini coefficients, no P-values). The audience is a controller or accounting manager, not a data scientist.

### Customizing the digest

The `generate_digest.py` script produces a solid default. Review it and make light edits if needed — for example, adjusting the headline or adding context the script can't know (like "this was the first close after the ERP migration"). Don't rewrite the whole thing.

Read `references/questions.md` for the full question bank. If specific questions from the bank aren't covered by the default digest but are answerable from the data, add them.

---

## Step 5: Present to user

Show the digest inline so the user can read it without opening a file. Then ask:

**"Want me to post this to a Slack channel?"**

If yes:
- Ask which channel (use `slack_search_channels` to help find it)
- Post using `slack_send_message`
- Confirm with the message link

If no: done.

---

## Step 6 (optional): HTML dashboard

Only build if the user explicitly asks for a visual dashboard. When they do:

Create a single-file HTML at `<output_dir>/close-retro-<workspace>-<period>.html` using inline CSS and Chart.js via CDN. Include:

- **Scorecard tiles**: completion %, cycle time, median turnaround, late %, back-loading score
- **Pace chart**: completions per day with cumulative overlay
- **Late tasks table**: task name, assignee, due date, completed date, days late
- **Review friction table**: task name, preparer, reviewer, reopen count
- **Assignee leaderboard**: per-person metrics with task type mix

Keep the style clean — light background, muted colors (blues for progress, amber for warnings, red for late/friction).

---

## Performance notes

These learnings come from real usage and save significant time:

1. **Always parse MCP results with the bundled scripts.** The raw MCP responses are 50–300K characters. Trying to process them in-context is slow and error-prone. The scripts extract exactly what's needed.

2. **Extract the user map early.** Event data contains user IDs, not names. Parse the workspace context first so you have the ID→name mapping before processing events.

3. **Batch events by task_keys, ~15 per batch.** The events API returns 500 on unfiltered calls. Batching by 15 task keys keeps response sizes manageable (70–190K per batch).

4. **Batch events proportionally.** For workspaces with many tasks, you don't need events for every single task. 6–10 batches of 15 keys each (90–150 tasks) gives reliable medians and distributions. Scale up for smaller workspaces where full coverage is quick.

5. **Event batches are the bottleneck.** Each batch takes a few seconds to return and the responses are large (70–190K). Plan the number of batches based on total task count — don't over-fetch for small periods or under-fetch for large ones.

6. **Don't build the HTML dashboard by default.** The Slack digest is what people actually use. The dashboard is nice for presentations but isn't worth the extra build time unless requested.

---

## Edge cases

- **Zero tasks in period:** Report "No tasks found" and stop.
- **No events returned:** Skip efficiency metrics. Report only status-based metrics from the task list.
- **No due dates on tasks:** Exclude from late-task analysis. Note the gap in the digest.
- **No prior period:** Skip period-over-period comparison.
- **Open period:** Label everything as "progress to date." Replace cycle time with "Day X of Y."
- **Negative turnaround values:** Some tasks have assignments recorded after submission (data quirk). The compute script filters these out automatically.
- **Self-review tasks:** Flag but don't count as a process failure — some workspaces intentionally use self-review for low-risk tasks.
