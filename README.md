# Numeric MCP Toolkit

A collection of AI skills for the [Numeric MCP](https://help.numeric.io/articles/7292808089-numeric-mcp-server). [Numeric](https://numeric.io) is an AI close automation platform that unifies close management, reporting, and cash for complex accounting teams.

Each skill is a purpose-built workflow that handles the full sequence of steps for you: connecting to Numeric, pulling the right data, applying logic, and producing a finished output. Tasks that would normally take 10–20 minutes of manual work — exporting data, cross-checking accounts, formatting a workbook — happen in a single conversation. No scripting, no manual data wrangling, no context switching.

---

## Plugin vs. individual skills

**Install as a plugin** if you want everything in one step. A `.plugin` bundles all nine skills with a single install — Cowork or Claude Code registers them all at once and they're immediately available. This is the recommended approach for teams rolling this out to multiple people.

**Install individual skills** if you only want one or two workflows, or if you're already managing your own skills directory and want to be selective. Each skill is self-contained and works independently.

---

## Install options

### Option 1 — Complete .zip file (easiest)

1. Download [`numeric-toolkit.zip`](../../releases/latest) from the Releases tab
2. Open [claude.ai](https://claude.ai) and click **Customize** in the left nav
3. Go to **Plugins** and upload the zip — all nine skills will be installed

### Option 2 — Claude Code Marketplace

Run these two commands in Claude Code:

```
/plugin marketplace add geoff-lew/numeric-toolkit
/plugin install numeric-mcp-toolkit
```

Then run `/reload-plugins` to apply.

### Option 3 — Individual skill upload

1. Download any `.skill` file from the [Releases tab](../../releases/latest)
2. Open [claude.ai](https://claude.ai) and click **Customize** in the left nav
3. Go to **Skills** and upload the `.skill` file

---

## Requirements

All skills connect to Numeric via the Numeric MCP at `https://api.numeric.io/mcp`. You'll need a Numeric account and to authenticate when prompted.

---

## Skills

| Skill | What it does |
|---|---|
| **numeric-rec-workbook** | Builds a Numeric Leadsheet .xlsx for any GL account — 4 periods of balance data + a rollforward tab |
| **dept-anomaly-scan** | Scans a workspace for GL-to-department miscodings and generates a NetSuite CSV journal entry to reclass them |
| **cross-workspace-dashboard** | Rolls up close progress across multiple Numeric workspaces into a portfolio HTML dashboard + Excel workbook |
| **audit-evidence-export** | Pulls the full activity history for a close period (submissions, approvals, review notes) into a formatted Excel workbook for auditors |
| **close-pulse** | Close management dashboard — materiality flags, overdue tasks, completion rate, pace, and dependency mapping |
| **consolidated-flux** | Merges flux variance commentary across entities, reports, and periods into one unified view |
| **financial-metrics** | Computes standard financial ratios inline on the income statement and balance sheet — margins, liquidity, working capital, covenants |
| **clean-report-export** | Exports any Numeric financial statement as a clean CSV/TSV with no junk rows, ready for Excel or BI tools |
| **executive-report** | Generates a board-ready or CFO-ready financial statement — collapses child detail into summary groups, rolls up flux commentary, outputs styled Excel or PDF |

---

## Support

Questions or issues? Email [support@numeric.io](mailto:support@numeric.io).

---

## License

MIT
