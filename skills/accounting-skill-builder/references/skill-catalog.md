# Skill Catalog — Numeric MCP Toolkit

Existing skills the Numeric Integration agent uses as baseline candidates. When a workflow maps to one of these, the recommendation is "refine [skill]" rather than greenfield.

For each skill: what it does, the trigger shape that signals fit, and common refinement levers.

---

## close-pulse
**Does:** Manager dashboard for close status across checklist, recon, and flux modules. Five lenses — materiality, urgency, progress, pace, dependencies.
**Trigger fit:** "How's the close going", "what's overdue", "close dashboard", "are we on track".
**Refinement levers:** Lens selection, materiality threshold, single-period vs. trend, daily artifact vs. on-demand run.

## close-retro
**Does:** Post-close retrospective. Analyzes pace, review quality, workload balance, setup gaps. Slack digest by default; HTML dashboard optional.
**Trigger fit:** "How did the close go", "close retro", "what took longest", "who was late".
**Refinement levers:** Question bank scope, batch sizing for events, dashboard vs. digest output, materiality gate for which tasks to drill into.

## automatically-draft-flux-explanations
**Does:** Drafts flux explanations for all GL accounts assigned to the user where flux is requested. Pulls 6 months of transactions, drafts conclusion-first explanations, posts to Numeric.
**Trigger fit:** "Draft my flux", "do my flux for this month", "write flux for close".
**Refinement levers:** Materiality gate (skip <$5K and <10%), lookback window, draft tone, IS-first vs. BS-first ordering, append-with-divider behavior.

## complete-accruals-task
**Does:** End-to-end accrual task completion. Pulls vendor spend history, identifies candidates, generates workpaper + JE CSV, submits the task with structured comments. Saves preferences to task description for next month.
**Trigger fit:** "Run accruals", "complete accrual task", "accrue vendors".
**Refinement levers:** Trigger criteria (zero-spend, MoM threshold, minimum amount), estimation method priority, exclusion list, lookback window, manual vendor additions.

## journal-entry-generator
**Does:** Generates and posts NetSuite journal entries from source documents. Pulls pending JE tasks, parses source files, classifies lines, builds workpaper, validates DR=CR, optionally posts via `ns_createRecord`.
**Trigger fit:** "Book this invoice", "post this JE", "month-end entries".
**Refinement levers:** Classification rules, validation rule set, External ID pattern, post vs. download CSV, batch vs. single task.

## dept-anomaly-scan
**Does:** Scans for GL-to-department coding anomalies, drills into transactions, generates a NetSuite reclass JE CSV.
**Trigger fit:** "Department anomalies", "GL miscodings", "scan for reclass entries".
**Refinement levers:** Universal vs. industry-specific rule set, materiality gate, drill window, "always keep new large items" carve-out.

## numeric-rec-workbook
**Does:** Generates a Numeric Rec workbook (.xlsx) for any GL account with leadsheet + rollforward, balances pulled from Numeric.
**Trigger fit:** "Build rec support for [account]", "leadsheet for [account]", "rollforward workbook".
**Refinement levers:** Account scope, entity scope, period range, additional tabs.

## rec-to-numeric
**Does:** Converts a customer's BS-Rec assignments file into a Numeric Rec Assignment import xlsx.
**Trigger fit:** "Build rec import", "convert BS rec assignments", "import balance sheet recs".
**Refinement levers:** Column mapping overrides, account number swaps, preparer/reviewer email maps.

## checklist-to-numeric
**Does:** Converts a close checklist (FloQast, BlackLine, Trintech, Workiva, custom xlsx/csv) into a Numeric-ready import workbook.
**Trigger fit:** "Convert FloQast to Numeric", "migrate close checklist", "import checklist".
**Refinement levers:** Column mapping overrides, frequency parsing, deadline format (BD vs. calendar).

## audit-evidence-export
**Does:** Extracts complete activity history for a close period and produces a formatted Excel workbook for external audit.
**Trigger fit:** "Audit evidence", "evidence of review", "SOX evidence", "activity export for auditors".
**Refinement levers:** Period scope, module scope (checklist/recon/flux), formatting style, sign-off filtering.

## consolidated-flux
**Does:** Consolidates flux variance commentary across entities, reports, accounts, and periods into a unified view.
**Trigger fit:** "Consolidate flux", "roll up variance commentary", "cross-entity flux".
**Refinement levers:** Dimension selection (entity / report / account / period), materiality rollup threshold, narrative depth.

## clean-report-export
**Does:** Generates a clean, analysis-ready CSV/TSV from any Numeric report — strips summary rows, fixes formatting.
**Trigger fit:** "Export the income statement", "clean CSV from Numeric", "report data for Excel".
**Refinement levers:** Output format (CSV/TSV/xlsx), column subset, multi-report batch.

## executive-report
**Does:** Board-ready or CFO-ready financial statement. Collapses child accounts to executive groups, rolls up flux to one-line narratives.
**Trigger fit:** "Board report", "CFO report", "presentation-ready financials".
**Refinement levers:** Group definitions, comparison period (prior month / quarter / year / budget), single vs. multi-entity, output format (xlsx vs. PDF).

## financial-metrics
**Does:** Computes and appends standard financial ratios — profitability, covenant/liquidity/solvency, working capital — to any Numeric report.
**Trigger fit:** "Gross margin", "covenant ratios", "DSO", "calculate ratios", "liquidity check".
**Refinement levers:** Ratio set selection, output placement (append to existing report vs. standalone), benchmark thresholds.

## ar-ap-aging
**Does:** Builds an AR or AP aging from Numeric. Classifies trade vs. journal, FIFO-matches reductions, buckets open balances, GL reconciliation row.
**Trigger fit:** "AR aging", "AP aging", "who owes us", "vendor aging".
**Refinement levers:** Bucket definitions, trade vs. journal classification rules, customer/vendor scope, currency.

## cross-workspace-dashboard
**Does:** Multi-entity executive close dashboard. Rolls up multiple Numeric workspaces into a portfolio-level HTML dashboard with companion Excel workbook.
**Trigger fit:** "Portfolio close", "close across all entities", "controller dashboard".
**Refinement levers:** Entity selection, comparison metrics, HTML vs. Excel-only.

## report-txn-detail
**Does:** Pulls any Numeric report (IS, BS, saved config) and produces an Excel workbook with the report + a flat table of every GL transaction line behind it.
**Trigger fit:** "Report with transaction detail", "GL detail behind the report", "drill-down".
**Refinement levers:** Report selection, transaction filter, format.

## overdue-task-nudge
**Does:** Sends Slack reminders for overdue or upcoming-due Numeric tasks. Reads preferences from task descriptions, logs reminders as comments to prevent duplicates.
**Trigger fit:** "Remind people on overdue tasks", "send close reminders", "chase outstanding recs".
**Refinement levers:** Reminder cadence, message tone, channels, escalation rules.

---

## How to use this catalog

When the Numeric Integration agent reads a brief:

1. Match the workflow against trigger fits above. If multiple match, prefer the most specific.
2. If a fit exists, the recommendation is `refine: <skill>` with the relevant levers spelled out for the user's specific workflow.
3. If no fit exists, the recommendation is `greenfield` and the agent describes why no existing skill covers the spine.

The plan should always show the existing-skill check, even when greenfielding — that demonstrates the agent considered reuse first.
