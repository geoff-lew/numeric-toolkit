# Build Patterns

How to build the deliverable in Phase 3. Methodology for skill scaffolding, script writing, integration wiring, and run-doc authoring. Read at Phase 3, not upfront.

For skill-specific best practices (frontmatter, progressive disclosure, examples), invoke the `skill-creator` skill — don't duplicate its content here.

## Output types and control discipline

The deliverable is always a Cowork skill, but what the skill *produces when run* varies. Each output type has a different control bar.

### Report (Excel, PDF, HTML, Slack message)
- Read-only artifact for review. No mutation, no confirmation gate needed.
- Conclusion-first structure: headline numbers up top, supporting detail below.
- Excel → invoke the `xlsx` skill for formatting discipline.
- PDF → invoke the `pdf` skill.
- Slack message → match the user's typical message style; structured content beats walls of text.

### External mutation (NetSuite JE posted, Numeric task submitted, flux explanation updated)
- Default to dry-run; require `--apply` flag (or equivalent) to actually mutate.
- Idempotency key on every call — re-running the same period must not double-post.
- Pre-call validation: DR=CR before `ns_createRecord`, account resolves, period not locked, External ID format correct.
- `AskUserQuestion` confirmation gate before any mutation lands.
- Audit trail: post a Numeric task comment summarizing what was done.

### Working file (rec workbook, leadsheet, allocation workbook)
- Excel with formulas (formula-first; values come from formulas, not hardcoded).
- Reference the `xlsx` skill for layout conventions.
- Cell references survive when source data updates.
- Color discipline: pulled-from-system in blue, user-entered in black, formulas in default.

### Cowork artifact (live HTML dashboard)
- HTML calls the connector at open-time via `window.cowork.callMcpTool`.
- Refresh discipline: data fetched on open; show last-fetched timestamp.
- Use `mcp__cowork__create_artifact`.
- Don't bake stale data into the HTML.

### Composite (multi-step producing several outputs)
- Multi-step workflow that produces several outputs (e.g., generate workpaper → post JE → submit task).
- Wire each step's output as the next step's input.
- Confirmation gates between steps that mutate.
- Single run-doc walks the user through the full chain.

## The four sub-roles

Build covers four sub-roles depending on what the plan calls for. One agent does all four; sub-roles trigger by need.

### Skill Scaffolder
Triggered when the plan calls for a Cowork skill (almost always — the deliverable is always a skill).
- Invoke the `skill-creator` skill for frontmatter, progressive disclosure, output formats, examples.
- All domain logic lives in `references/`, never SKILL.md prose.
- For refinement of an existing toolkit skill: copy the existing SKILL.md as starting point, apply the levers from `plan/numeric-integration.md`.

### Script Writer
Triggered when the plan calls for code (almost always — most skills have a `scripts/` folder).
- Python with declared `--break-system-packages` installs at the top.
- Dry-run mode by default; `--apply` flag to mutate.
- Idempotent — re-running on the same period does not double-post.
- Logs every external call.
- Short-circuits on empty.
- Inline doctests where helpful.

### Integration Writer
Triggered when the deliverable touches Numeric, NetSuite, or another connector.
- Wraps every external call in retry shim with idempotency key.
- Validates inputs before the call (DR=CR before `ns_createRecord`, account resolves, period not locked).
- Filters server-side wherever the API allows (push filters into the MCP call per `references/performance-patterns.md`).
- Caches cold-start calls per `references/numeric-mcp-principles.md`.
- Posts task comments for audit trail.
- Writes preferences to task description for next-cycle pickup.
- Submission gate: never submit without explicit user confirmation.

### Run Doc Writer
Triggered always — every deliverable has a one-page how-to.
- Title: what this does
- When to run
- What to type / upload
- What output to expect — including the **specific output path** so Phase 4 reviewers know where to look
- What to check before approving
- The streaming-progress messages the user will see
- The `AskUserQuestion` gates and what each option means
- A **"How to test this for review"** section: tells the user the exact command to run with safe defaults — recent closed period, dry-run flag, sample data option. This is what the user uses to produce the test output that Phase 4's panel will review. Without this, the user has to invent their own test invocation, and the panel reviews inconsistently.

## Design checklist

While writing the deliverable, every applicable item from `references/performance-patterns.md` is wired in:

- [ ] Cold-start cache scaffolding (if Numeric-touching)
- [ ] Materiality gate parameterized
- [ ] Subagent contract followed if fan-out is used
- [ ] Confirm-scope `AskUserQuestion` before expensive pulls
- [ ] Cap parallel calls at 3
- [ ] Server-side filtering on `list_tasks` etc.
- [ ] Short-circuit on empty wired
- [ ] Mutating operations gated by `AskUserQuestion` confirmation
- [ ] Streaming progress per subagent return
- [ ] Validate scope before parsing/pulling
- [ ] Default windows; confirm before widening

If a pattern doesn't apply (no fan-out, no Numeric calls, etc.), say so explicitly in the deliverable's `performance.md`.

## Predictable output paths

The deliverable's run-doc and the deliverable itself must agree on output paths. Phase 4 reviewers look for outputs at well-known paths; if the skill saves to ad-hoc locations the panel can't find them. Conventions:

- Workpapers and reports → `{user_workspace}/{deliverable_name}/output/{period}/`
- Captured run logs → `{user_workspace}/{deliverable_name}/output/{period}/_run_log.md`
- JE / mutation CSVs (dry-run) → `{user_workspace}/{deliverable_name}/output/{period}/_pending/`
- Audit trail (task comments, etc.) → captured in a markdown summary, not inferred from external systems

The deliverable's `performance.md` and run-doc both reference these paths.

## Deliverable file tree

`{run_id}/build/` contains:

```
{run_id}/build/
├── {deliverable_name}/         # The skill the user copies to their workspace
│   ├── SKILL.md
│   ├── references/             # Domain logic for this skill
│   ├── scripts/                # Bundled scripts
│   └── performance.md          # Scoped performance discipline for this skill
├── _build_summary.md           # One-pager listing every file + why
└── _panel_inputs.md            # Paths the Phase 4 panel will read
```

The user copies `{deliverable_name}/` (just that directory) to their workspace folder. Cowork picks up the new skill. `_build_summary.md` and `_panel_inputs.md` stay in the build run output for the audit trail.

## Deliverable's own performance.md

When the deliverable is substantial (a skill, a composite workflow, anything with fan-out), Build produces a scoped `performance.md` in the deliverable's `references/`. Pure reports or one-shot working files probably don't need one — use judgment.

When included, the structure mirrors the toolkit performance.md files: cache cold-start, confirm scope upfront, fan out independent units, cap parallel at 3, subagent contract, push parsing to scripts, materiality gate, push filters into MCP, checkpoint between phases, validate scope, short-circuit on empty, stream progress, repeat-use → artifact, default windows. Each item references the deliverable's specific cache keys, scripts, materiality defaults, etc.

This file ships with the deliverable so the next person extending it knows the design intent.

## Constraints

- Don't run the automation. Phase 4 runs it. Build constructs only.
- Don't auto-mutate. Every mutating path defaults to dry-run with a confirmation gate.
- Refinement default: when the plan said `refine: <skill>`, copy the existing skill as the base and apply levers. Don't rewrite from scratch.
- Output is files, not narrative. The build summary ("here's what I made") is one paragraph; the deliverable speaks for itself.
