# Numeric Toolkit

Nine Cowork / Claude Code skills for the [Numeric](https://numeric.io) financial close platform. Connect to any Numeric workspace and run close operations, analytics, and exports directly from your AI assistant.

## Install

**As a plugin (one-click)**
Download `numeric-toolkit.plugin` from [Releases](../../releases/latest) and open it in Cowork or Claude Code.

**Via Claude Code CLI**
```
claude plugin install https://github.com/thedotmack/numeric-toolkit
```

**Individual skill**
Browse `skills/` and copy any `SKILL.md` into your own skills directory.

## Requirements

Connect the [Numeric MCP](https://api.numeric.io/mcp) — all skills call the Numeric API directly. Authenticate with your Numeric account when prompted.

## Skills

| Skill | What it does | Trigger phrases |
|---|---|---|
| **numeric-rec-workbook** | Builds a Numeric Leadsheet .xlsx for any GL account — 4 periods of balance data + rollforward tab | "build rec support for account 1200", "make the leadsheet for Prepaid", "create a workbook for account 1405" |
| **dept-anomaly-scan** | Scans a workspace for GL-to-department miscodings and generates a NetSuite CSV journal entry to reclass them | "department anomalies", "scan for miscodings", "generate reclass entries", "department audit" |
| **cross-workspace-dashboard** | Rolls up close progress across multiple Numeric workspaces into a portfolio HTML dashboard + Excel workbook | "cross-workspace close dashboard", "portfolio close", "which entities are behind", "CFO dashboard" |
| **audit-evidence-export** | Extracts full activity history (submissions, approvals, review notes) for a close period into a formatted Excel workbook for auditors | "audit evidence", "SOX evidence", "export close activity", "auditor workpaper" |
| **close-pulse** | Close management dashboard across five lenses: materiality, urgency, progress, pace, and dependencies | "close status", "what's overdue", "close pulse", "how's the close going", "who's behind" |
| **consolidated-flux** | Merges flux variance commentary across entities, reports, accounts, and periods into one unified view | "consolidate flux", "roll up variance commentary", "flux summary for CFO", "cross-entity variance" |
| **financial-metrics** | Computes standard financial ratios inline on the IS and/or BS — margins, liquidity, working capital, covenants | "gross margin", "current ratio", "EBITDA", "financial ratios", "add metrics to my balance sheet" |
| **clean-report-export** | Exports any Numeric financial statement as a clean CSV/TSV — no junk rows, ready for Excel or BI tools | "export a report", "clean CSV", "pull the income statement into Excel", "export for analysis" |
| **executive-report** | Generates a board-ready or CFO-ready financial statement — collapses child detail, rolls up flux commentary, Numeric-styled Excel or PDF | "executive report", "board report", "CFO report", "board package", "roll up the P&L" |

## Marketplace

Submit for listing in the Anthropic community plugin directory at [clau.de/plugin-directory-submission](https://clau.de/plugin-directory-submission). Once approved, installable via `/plugin install numeric-toolkit`.

## License

MIT
