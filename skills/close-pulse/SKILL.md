---
name: close-pulse
user-invocable: true
description: >
  Manager dashboard for close status across checklist, recon, and flux modules. Five lenses: materiality, urgency, progress, pace, and dependencies. Use when the user asks for "close status", "what needs attention", "close dashboard", "how's the close going", "what's overdue", "who's behind", "close progress", "show me what's open", "are we on track", "close pulse", "daily close digest", "close completion rate", "pace of close", "materiality flags", "what accounts are over threshold", "close management summary", or any request about close status, progress, bottlenecks, or task urgency.
---

# Close Pulse

Unified close management dashboard. Five lenses, each answerable independently or combined. Auto-detect the relevant module (checklist, recon, flux) from report context, or go cross-module if the user asks for "everything."

## Setup

1. Call `get_workspace_context` to get the current period, users, holidays, and entities
2. Call `list_reports` to discover all report configs and their types
3. Identify the target period — default to the most recent open period unless the user specifies

## Lens Selection

Ask the user which lens they want, or infer from their question:

| User says | Lens |
|---|---|
| "what's material", "over threshold", "big variances", "recon variances" | Lens 1: By the Numbers |
| "what's overdue", "who's behind on dates" | Lens 2: By the Dates |
| "close progress", "how far along", "completion rate" | Lens 3: By the Progress |
| "are we ahead or behind", "close pace", "trending" | Lens 4: By the Pace |
| "what's blocked", "dependencies", "critical path" | Lens 5: By Dependencies |
| "everything", "full dashboard", "close pulse" | All 5 lenses |

If unclear, start with Lens 3 (progress) as the default — it's the most universally useful.

See `references/lenses.md` for detailed implementation of each lens.

## Cross-Module Detection

Determine which modules are relevant:

1. Look at report configs from `list_reports` — the report name/type usually indicates whether it's a checklist, recon, or flux report
2. If the user specifies a module ("flux status", "recon overdue"), scope to that module
3. If the user says "everything" or "across the board", run across all report types

## Output Formats

- **In-chat digest**: default for quick status checks. Markdown formatted summary.
- **Slack post**: if the user says "post to Slack" or "send to channel", format as a Slack message (requires Slack MCP)
- **Formatted file**: if the user wants to save/share, output as xlsx or markdown file

## Actions

Some lenses support follow-up actions:

- **Lens 2**: batch-post @mention reminders via `add_task_comment` for overdue items. Only do this if the user explicitly asks. Can chain with the `schedule` skill for recurring daily nudges.
- **Lens 3**: offer to drill into specific assignees or reports that are behind

Always confirm before taking action on tasks — this is a read-first, act-second skill.

## Output Guidelines

Present the data for each lens directly — do not append a "Summary" or "Recommended Actions" section at the end. The lens outputs themselves are the deliverable. Let the user decide what to act on rather than prescribing next steps.

## Performance

Cache cold-start calls within the session. Fan out lens computations when all five are requested. For daily users, suggest a Cowork artifact instead of regenerating each morning. See `references/performance.md` for the full pattern.
