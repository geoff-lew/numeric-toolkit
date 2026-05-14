# Plan — {workflow_name}

**Run ID:** {run_id}
**Brief:** [link to brief.md]

## Summary
[Three sentences. Delivery shape, attachment to Numeric (or not), critical risk.]

## Approach
[One paragraph describing the automation. What it pulls, what it computes, what it produces, what mutates.]

---

## Data sources
[From `plan/data-sources.md`. Headline: N reachable, K gaps. Then the table.]

| Data | Source | Access method | Auth | Volume | Reachable? | Gap |
|---|---|---|---|---|---|---|
| ... | ... | ... | ... | ... | ... | ... |

## Accounting controls
[From `plan/accounting.md`. Headline: workflow type, N controls, materiality.]

### Workflow type
[type]

### Industry pack applied
[name]

### Controls checklist
**Mathematical**
1. ...

**Structural**
N. ...

**Business logic**
N. ...

**Type-specific**
N. ...

### Materiality
$X. Rationale: ...

### Human-in-the-loop
- Before mutate: ...
- Post-run review: ...
- Unattended: ...

### Risks and manual checks
- ...

## Numeric integration
[From `plan/numeric-integration.md`. Headline: refine vs. greenfield, attachment type.]

### Existing skill check
Recommendation: ...
[refinement levers OR greenfield justification]

### Attachment
Type: ...
MCP calls: ...

### MCP principles applied
- Persistence: ...
- Audit trail: ...
- Cold-start: ...
- API-side filters: ...
- Submission gate: ...
- Period awareness: ...
- Sizing: ...

## Pushbacks
[From `plan/pressure-test.md`. Headline: K pushbacks found. Most consequential: ...]

[Numbered list of pushbacks, each with the brief quote, the specific question, and the lens.]

### User's response to pushbacks
[Captured after the user reviews. Each pushback marked: addressed (with how) | dismissed (with reason) | will revisit later.]

## Architecture
[From `plan/architecture.md`. Headline: delivery shape, runtime, scope.]

### Delivery shape
[refinement | new skill | artifact | scheduled task | script]

### Runtime
[where it runs]

### File layout
- ...

### Scope estimate
- File count: N
- Build wall time: T min
- Token cost: K
- Risk areas: ...

### User confirmation
[the user's answer to the AskUserQuestion gate]

---

## What Build will produce
[Synthesized from the four agent outputs. The user reads this and either approves or asks for revisions.]

## Risks and rollback
[Cross-cutting risks the four agents surfaced. Rollback plan if Phase 4 fails the controls.]
