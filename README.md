<div align="center">

<br />

<img src="assets/NumericLogo-Black-2025.png" width="200" alt="Numeric" />

<h1>Community Skills for the Numeric MCP</h1>

<h3>Purpose-built AI workflows for accounting teams on Numeric</h3>

<p><a href="https://numeric.io">Numeric</a> is an AI-native accounting platform. The <a href="https://help.numeric.io/articles/7292808089-numeric-mcp-server">Numeric MCP</a> connects it directly to your AI assistant.<br/>These community-built skills turn that connection into ready-to-run accounting workflows.</p>

<br />

<a href="https://github.com/geoff-lew/numeric-toolkit/releases/latest/download/numeric-mcp-toolkit.plugin">
  <img src="https://img.shields.io/badge/⬇%20Download%20Full%20Plugin-numeric--mcp--toolkit.plugin-3E3A7A?style=for-the-badge&logoColor=white" alt="Download Full Plugin" />
</a>
&nbsp;
<a href="https://geoff-lew.github.io/numeric-toolkit/">
  <img src="https://img.shields.io/badge/Browse%20Skills%20Library-→-1F0045?style=for-the-badge" alt="Browse the live skills library" />
</a>
&nbsp;
<a href="https://github.com/geoff-lew/numeric-toolkit/releases/latest">
  <img src="https://img.shields.io/badge/View%20Releases-363644?style=for-the-badge" alt="View Releases" />
</a>

<br />

<br />

</div>

---

## What is Unlocked with the Numeric MCP

The [Numeric MCP](https://help.numeric.io/articles/7292808089-numeric-mcp-server) is an open protocol connection that gives your AI assistant direct, authenticated access to your Numeric workspace — live data, real actions, no copy-paste.

With it connected, Claude can read and write across your entire close stack:

<table>
<tr>
<td width="33%" valign="top">

### Workspace Intelligence
Understand your org structure, open periods, team members, entities, GL connections, and permissions — without you having to explain any of it.

</td>
<td width="33%" valign="top">

### Close Operations
Full task lifecycle access — create, assign, update, submit, approve, comment, and audit across any period and any entity. Bulk operations in seconds.

</td>
<td width="33%" valign="top">

### Financial Data
Pull any saved report, build ad-hoc financials on the fly, trend period-over-period data, and drill all the way down to individual journal entry lines.

</td>
</tr>
</table>

**And because MCP is an open standard, Numeric connects naturally with the other tools your team already uses:**

- **Slack MCP** — Post close status updates, send targeted task reminders, and trigger alerts when variances exceed thresholds — all automated, no manual messaging
- **Gmail & Google Calendar MCP** — Draft close status emails for leadership, auto-block close windows in team calendars based on Numeric due dates, send auditor prep packets
- **NetSuite MCP** — Post journal entries directly into NetSuite from a conversation, completing the full loop from accrual identification to posting without leaving Claude

> The Numeric MCP exposes 19 tools across workspace management, close task operations, and financial reporting. Anything you can do in Numeric's Insights feature is now available through Claude — with the ability to chain queries, combine data across systems, and produce formatted outputs you can share directly.

---

## How Numeric and the Numeric MCP Fit Together

**Numeric is the operating system for your accounting team.** Like any OS, it manages state — who owns what, what's been done, what the rules are, what happened last period. Your team runs on top of it. Your processes are encoded in it. Your institutional knowledge accumulates inside it.

Use task descriptions to store how a workflow should run. Reference prior period commentary to understand recurring patterns. Record preferences, exceptions, and policies directly in Numeric so they carry forward automatically — not locked in someone's head or buried in a spreadsheet.

**The Numeric MCP is what lets your AI run on that operating system.** It exposes Numeric's full state to Claude — live tasks, financial data, team structure, history, commentary — and it's bidirectional. The AI doesn't just read; it writes results back, updates tasks, posts comments, and keeps the record current. An AI connected via the MCP isn't answering generic questions; it's operating with full awareness of your team and where things stand right now.

**Together, the MCP supercharges what Numeric can do natively.** Numeric tracks the work — the MCP executes it. Draft flux explanations across every assigned account in one run. Identify accrual candidates from transaction history and post the journal entries. Send targeted Slack reminders based on who's behind and what preferences you've set. Everything that would otherwise require manual steps, a separate script, or a tool outside Numeric can now happen directly from a conversation — with results written back into Numeric where they belong.

Skills in this toolkit are built on that model.

<div align="center">
<br/>
<img src="assets/Numeric MCP stack.png" width="100%" alt="Numeric MCP Stack" />
<br/>
</div>

---

## Browse the Skills Library

The full catalog lives at **[geoff-lew.github.io/numeric-toolkit](https://geoff-lew.github.io/numeric-toolkit/)** — search, filter by role or type, and download individual skills.

Skills are grouped into seven categories:

- **Setup & Migration** — checklist and rec-assignment imports, skill-building
- **Journals & Transactions** — accruals, journal entry posting, department-anomaly scans
- **Close Management** — close pulse, retro, overdue nudges, cross-workspace dashboard, checklist diagnostic
- **Flux & Variance** — auto-drafted flux explanations, consolidated commentary rollup
- **Reporting & Analysis** — board-ready statements, transaction-detail reports, clean exports, financial ratios, AR/AP aging
- **Reconciliation** — leadsheet workbook builder
- **Audit & Compliance** — close-period activity export

All skills connect to Numeric via the Numeric MCP. Each is fully self-contained — download the `.skill` file, drop it into Cowork or Claude Code, done.

---

## Tips

### Use your close checklist to drive automations

Your Numeric close checklist is more than a task list — it's the control plane for your close workflow. Skills read task status, due dates, assignees, and descriptions directly from the checklist, which means your existing tasks can help to drive your workflows by instructing your AI to take specific actions.

For example: create an *Accruals* task in Numeric with a due date of day 3. The accrual skill reads the list of tasks, knows what's expected and if any need to be handled, runs the workflow, and marks it complete — all triggered by a single instruction.

### Use task descriptions to carry preferences and instructions forward

You can store workflow preferences and specific instructions directly in a task description, and the skill will read them on every run. Use this to note any changes you want applied going forward — no need to re-specify them each time.

```
## Skill preferences
- Reminder cadence: only send nudges if 48+ hours since last reminder
- Output format: Excel workbook, save to /Close Workpapers/Prepaid/
- Reviewer: Tag Sarah in the Slack message when complete
```

### Let skills self-track via comments

Skills can automatically log a comment on the relevant Numeric task after they run — recording what was done, when, and what the outcome was. This creates a native audit trail inside Numeric and lets skills make smart decisions on subsequent runs. For example, the overdue nudge skill will check the comment history before sending a reminder, so it won't re-notify someone if they were already nudged in the last 48 hours.

### If a skill doesn't trigger automatically, be explicit

Skills activate based on how you phrase your request. If Claude responds without using the right skill, just tell it directly which one to use:

> *"Use the close-pulse skill to show me where the close stands."*
> *"Run the automatically-draft-flux-explanations skill for this period."*

You can also ask Claude which skills are available: *"What skills do you have installed?"*

### Customize a skill to fit your workflow

Once installed, any skill can be refined to match your team's specific process. Open a conversation and ask Claude:

> *"Update the close-pulse skill so that it always groups overdue tasks by assignee first, skips tasks tagged 'on hold', and posts the summary to #accounting-close in Slack instead of responding in chat."*

Claude will modify the skill in place. Your customized version becomes the default for future runs — no coding required. Combine with task descriptions to give Claude a 'working memory'.

---

## Get Started

### 1. Connect the Numeric MCP

See the [Numeric MCP setup guide](https://help.numeric.io/articles/7292808089-numeric-mcp-server) to connect your workspace. Once authenticated, Claude has direct access to your Numeric data.

### 2. Install the skills

<table>
<tr>
<td width="50%" valign="top">

**Full plugin** — all skills at once

Download [`numeric-mcp-toolkit.plugin`](https://github.com/geoff-lew/numeric-toolkit/releases/latest/download/numeric-mcp-toolkit.plugin) and open it in Cowork or Claude Code.

Or via CLI — run these as separate commands:
```
/plugin marketplace add geoff-lew/numeric-toolkit
```
```
/plugin install numeric-mcp-toolkit
```

</td>
<td width="50%" valign="top">

**Individual skill** — just what you need

Browse the [skills library](https://geoff-lew.github.io/numeric-toolkit/) or grab any `.skill` file from the [Releases tab](https://github.com/geoff-lew/numeric-toolkit/releases/latest) and open it in Cowork or Claude Code.

Each `.skill` file is fully self-contained — no extra setup.

</td>
</tr>
</table>

### 3. Start working

Just describe what you need. The right skill activates automatically based on what you ask. No configuration required beyond authentication.

---

## Community & Contributing

These skills are built and maintained by the Numeric community. We welcome new skills — if you've built a workflow that saves your team time, share it and let others benefit too.

### How to contribute a skill

The easiest way: build the workflow you want in Claude, then ask it to *"bundle this into a skill"*. Claude will package it into the right format. Send it to [support@numeric.io](mailto:support@numeric.io) and we'll add it to the toolkit.

### Have an idea?

We're happy to help design and build new skills with you — whether it's a manual process you've been repeating every close, a recurring deliverable, or a workflow that would save your team hours each month. Reach out to [support@numeric.io](mailto:support@numeric.io) and tell us what you're trying to do.

---

<div align="center">

MIT License · Community-maintained · Built for [Numeric](https://numeric.io)

</div>
