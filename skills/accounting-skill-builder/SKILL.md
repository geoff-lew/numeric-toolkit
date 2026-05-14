---
name: accounting-skill-builder
metadata:
  user-invocable: true
description: >
  Builds a new Cowork skill for an accountant who wants to automate a workflow. Uses
  compound engineering — four phases (Ideate, Plan, Build, Review), each producing a
  document that becomes required input to the next. Plan fans out specialists (data,
  accounting controls, Numeric integration, architecture, pressure-test). Build
  assembles the new skill with performance discipline baked in. Review fans out a
  five-reviewer panel (controller, accounting process expert, auditor, adversarial,
  on-call) plus a synthesizer that renders one verdict. Trigger when the user says
  "build me a skill", "build an accounting skill", "automate this workflow",
  "automate my close process", "build me an automation", "compound automation",
  "ideate plan build review", "I want to automate [X]", "design an automation",
  "help me automate", or describes wanting to automate a repeatable accounting
  workflow. Use this skill even when the user does not name the framework explicitly.
---

# Accounting Skill Builder

Walks the user through automating an accounting workflow using compound engineering — each phase produces a doc that becomes the required input to the next, so context compounds rather than resets. Four phases — Ideate, Plan, Build, Review. Stop after Review.

The user is an accountant working in their own Cowork. They have access to the Numeric MCP Toolkit (existing skills covering close pulse, retro, flux, accruals, JE generation, rec workbooks, anomaly scans, audit evidence, AR/AP aging, etc.) plus their own connectors. The output of this skill is a working automation tailored to their workflow — most often a refinement of an existing toolkit skill, sometimes a new script or scheduled task, sometimes a Cowork artifact.

The four phases pin scope progressively: brief pins what to solve, plan pins how, build pins what's actually shipped, review pins what works.

## Phase 1 — Ideate

Load `agents/interviewer.md` and run the interview in the main thread. The interviewer covers the question flow with a thinking-partner stance — pushes back where framing is narrow, surfaces what the user didn't say. Stops as soon as the brief template can be filled and the user agrees the framing is right.

Pushback at this stage is conversational, in-the-moment. The deeper structural pushback (cross-cutting framing critique, adjacent-workflow surfacing, cadence and output-shape inversion) happens in Phase 2 via the pressure-test specialist.

Output: `{run_id}/brief.md` using `templates/brief.md`.

Gate to Phase 2: surface the brief, ask via `AskUserQuestion` whether to proceed, edit, or stop.

## Phase 2 — Plan

Plan happens in two passes.

**First pass — rough plan.** Synthesize the brief into a rough plan in the main thread. No subagents yet. Produce a high-level outline of the workflow steps the automation will run:

```
1. [step]: [what the automation does]
2. [step]: [what the automation does]
...
```

Include a guess at delivery shape (refinement of existing skill, new skill, scheduled task, artifact) and which existing toolkit skill (if any) is the closest fit. This pass is fast — maybe a paragraph plus the outline.

Surface the rough plan to the user. Ask via `AskUserQuestion` whether the workflow outline matches what they meant, what to change, or to add anything missing. Capture revisions inline.

**Second pass — specialists fill gaps.** Once the user signs off on the workflow outline, fan out the five specialist subagents in parallel via the Task tool, each reading the brief and the rough plan:

- `agents/data-sources.md` — maps required data and access paths; runs connectivity probes
- `agents/accounting.md` — applies the control taxonomy in `references/accounting-controls.md`
- `agents/numeric-integration.md` — confirms the existing-skill recommendation; codifies Numeric MCP interaction principles
- `agents/architecture.md` — finalizes delivery shape, file layout, and runs the scope-confirm gate
- `agents/pressure-test.md` — pushes back on the brief itself. Four lenses (pain/friction, inversion/removal, assumption-breaking, leverage/second-order). Surfaces gaps and questions the user should answer before Build.

Each writes to `{run_id}/plan/{agent}.md`. Parent merges into `{run_id}/plan.md` using `templates/plan.md`. Pressure-test's pushbacks surface to the user as part of the merged plan — user can revise the brief in response, dismiss specific pushbacks, or proceed.

Gate to Phase 3: surface the merged plan. Architecture's confirm-scope question runs here. User confirms or narrows.

## Phase 3 — Build

Build runs in the main thread. Read `brief.md` and `plan.md`, then construct the deliverable per the plan. Load `references/build-patterns.md` for the methodology — output types, sub-roles, design checklist, predictable output paths, deliverable file tree.

**The deliverable is always a Cowork skill.** When constructing the SKILL.md and its bundled files, invoke the `skill-creator` skill for skill-specific best practices (frontmatter, progressive disclosure, output formats, examples). Don't duplicate skill-creator's content.

**What the skill produces when run** varies — report / external mutation / working file / Cowork artifact / composite. The output type drives the skill's control discipline. See `references/build-patterns.md` for the discipline per type.

**Performance discipline.** Apply the patterns in `references/performance-patterns.md` while writing — caching, fan-out, materiality gates, scope-confirm gates, short-circuits, subagent contracts, gated submission. The new skill ships with its own scoped `performance.md`.

Output: `{run_id}/build/` containing the deliverable file tree, plus `_build_summary.md` (one-pager listing every file + why) and `_panel_inputs.md` (paths the Phase 4 panel will read).

Bridge to Phase 4: the user copies `{run_id}/build/{deliverable}/` to their workspace folder (e.g., `~/Documents/Claude/{deliverable}/`). Cowork registers the new skill. The user can now invoke it.

## Phase 4 — Review

Two steps with a synthesizer at the end. First, the user runs the new skill on test data themselves. Then a five-reviewer panel fans out in parallel against the captured outputs, and a synthesizer renders one verdict.

**Step 1 — User runs the new skill.** The user invokes the new skill on a recent closed period by default (or sample data, or synthetic input — they choose). Build's design defaults to dry-run mode; the user doesn't need a separate runner agent. Outputs land in the user's workspace folder under the run's chosen output path.

Before invoking the panel, confirm with the user: which run should the panel review? (Most recent run, named period, or specific output folder.) Capture the path — every panel reviewer needs it.

**Step 2 — Five-reviewer panel (parallel via Task tool).** Each reviewer receives three input paths:
1. The build artifacts at `{run_id}/build/{deliverable}/` (the skill source — SKILL.md, references/, scripts/, performance.md)
2. The user's test-run output path (whatever the user named in Step 1)
3. The brief and plan at `{run_id}/brief.md` and `{run_id}/plan.md` (for context — controls list, expected scope, materiality)

Each reviewer applies its own lens and returns structured JSON.

- `agents/controller-skeptic.md` — stakeholder lens. "Would I sign this with my name on the certification?"
- `agents/accounting-process-expert.md` — workflow-shape lens. Macro fit (S2P / O2C / R2R / H2R) and micro design (waste, variability, defects).
- `agents/auditor.md` — evidence lens. "Could a Big 4 senior rely on this control? Walk me through the population, sample, re-performance test."
- `agents/adversarial-reviewer.md` — failure-construction lens. Builds specific scenarios that break the deliverable (assumption violations, composition failures, cascades, abuse cases).
- `agents/production-on-call.md` — operational lens. "It's 3am Tuesday and this just failed. How does the user know? What's the runbook?"

Each writes to `{run_id}/review/{reviewer}.json`.

**Step 3 — Synthesize.** `agents/review-synthesizer.md` reads the user's test-run output, all five panel JSONs, and the brief (for the human-time baseline). Dedupes overlapping findings, triages everything P1 (must fix) / P2 (should fix) / P3 (nice to fix), and renders one verdict — Cleared / Cleared with conditions / Blocked.

The synthesizer writes the iteration backlog as a `## Iteration backlog (last reviewed YYYY-MM-DD)` section at the head of the delivered skill's `SKILL.md` (the one the user copied into their workspace folder). The user sees the backlog every time they re-open the skill.

Output: `{run_id}/review.md` using `templates/review.md`. End.

## Gotchas

Things that commonly go sideways. The orchestrator should watch for these.

- **Scope blur in Ideate.** The user describes two or three workflows that overlap. Pick one; surface the others as candidates for a separate run. Don't try to brief them all at once.
- **Industry tag captured wrong.** The interviewer should confirm SaaS / hardware / services / financial services explicitly via `AskUserQuestion` rather than inferring. Wrong tag → wrong control pack in Phase 4.
- **Brief missing a baseline time.** Performance can't compute time-saved without it. If the user doesn't know, ask for a rough range — "5 min, 30 min, half a day, full day."
- **User wants to skip Plan and jump to Build.** Push back. A Build without a Plan greenfields when refinement would have worked, and produces an automation Phase 4 can't validate against. Plan is non-skippable.
- **Greenfielding when an existing toolkit skill fits.** The Numeric Integration agent's check is supposed to catch this. If Build is producing a SKILL.md that looks a lot like an existing one, stop and re-check.
- **Phase 4 test run against an in-flight period.** Default to a recently-closed period for the first test run. In-flight periods change underneath the run and produce noisy panel-review results.
- **User wants to ship despite a Blocked verdict from the synthesizer.** Don't override. Surface the P1 findings, ask if they want to revise the plan, fix in-place, or mark specific findings as accepted risk (with a written justification that goes into the deliverable's audit trail).
- **Iteration backlog overwritten silently.** When the synthesizer rewrites the deliverable's `## Iteration backlog` section, items the user hasn't crossed off must carry forward. Older items don't disappear; only completed ones do.
- **Panel reviewers disagree.** Common — controller says ship, adversarial constructs a break, auditor finds an evidence gap. The synthesizer's job is judgment, not majority vote. Don't auto-resolve disagreements before synthesis runs.
- **Workspace cache stale.** Automations cache `list_financial_accounts` and `get_workspace_context` for 24h. If the user changed their chart of accounts or added entities, the cache will lie. Build should expose a `--refresh` flag that clears the cache.
- **Connector drops mid-run.** Build agents should wire idempotency so re-running on the same period doesn't double-post. Phase 4 surfaces this if it's missing.
- **Numeric task description hits the description size limit.** Preferences accumulate. Iteration agent should flag when the section is approaching ~10K chars and recommend pruning.
- **The user names a workflow that should be a connector, not a skill.** "I copy-paste from Slack to Notion every Friday" doesn't need an accounting-skill-builder run; it needs a Zapier / scheduled task. Bail to that recommendation in Phase 1.
- **Build produces files outside the workspace folder.** All build output must save under the user's selected folder so they have it after the session ends. The Build agent's run doc should be explicit about this.
