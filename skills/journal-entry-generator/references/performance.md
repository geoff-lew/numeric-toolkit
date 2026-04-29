# Performance patterns — journal-entry-generator

Most of the runtime is in source-file parsing, classification, and workpaper assembly. The skill already uses bundled scripts for the heavy lifting. Apply these patterns when running multiple JE tasks back-to-back.

## Use the bundled scripts

`scripts/build_workpaper.py` shapes the source data into the formula-first Excel output. `scripts/validate_je.py` verifies DR=CR before posting. Use them. Avoid re-deriving classification or balance logic inline.

## Fan out only when batching multiple tasks

A single JE task does not benefit from fan-out — the work is sequential within one task. When the user hands off multiple pending JE tasks at once, dispatch one subagent per task in a single Agent tool message. Each subagent owns its source file, runs the scripts, and returns the workpaper file path. Merge the posting step in the parent.

In environments without subagents, run tasks sequentially.

## Confirm scope before posting

The skill is high-stakes — JEs land in NetSuite. Do not post automatically. Surface the workpaper, the DR=CR validation result, and the planned External ID, then ask via `AskUserQuestion` whether to post via `ns_createRecord` or to download the CSV for manual import.

## Checkpoint between phases

Save the workpaper to `outputs/.je_cache/{period_id}/{task_id}/workpaper.xlsx` after Phase 2. If Phase 3 (post) fails, the next run resumes from the workpaper rather than re-parsing the source file.

## Cache the workspace context

`get_workspace_context` and `list_financial_accounts` change rarely within a session. Cache to `outputs/.numeric_session_cache/{workspace_id}.json` and reuse across multiple JE tasks in the same session.

## Validate scope before parsing

Before invoking `build_workpaper.py`, confirm:
- The source file exists and is readable.
- The pending JE task in Numeric is unambiguously matched.
- The subsidiary, External ID pattern, and required form fields (Department, Location, etc.) are confirmed from the task description.
- All referenced accounts resolve in `list_financial_accounts`.

A bad source file or unresolved account fails late, after the workpaper is half-built.

## Short-circuit on empty

If the source file produces 0 valid lines after classification, tell the user nothing posts and stop. Do not produce an empty CSV or push a balanced-by-zero JE.

## Stream progress

For multi-task batches, emit a one-line update per task (`"Built workpaper for 3 of 7 tasks..."`). Within a single task, emit at each phase boundary (`"Parsed source"`, `"Built workpaper"`, `"Validated DR=CR"`, `"Posted to NetSuite"`).

## Subagent prompt shape

When batching multiple JE tasks, each subagent receives:
- `task_id`, the source file path, the task description's instructions block, the cache path, the path to `build_workpaper.py` and `validate_je.py`.

Each subagent returns:
- `{task_id, workpaper_path: <xlsx>, csv_path: <csv>, dr_total, cr_total, balanced: bool}`.

Subagents have no conversation history. Do not assume access to NetSuite credentials or the workspace context — pass everything they need.
---

## v1.0 — additional patterns

### Confirm scope upfront when expensive work is implied

Before any heavy data pull, estimate the scope and confirm with the user via `AskUserQuestion` when any of these signals are present:

- Multi-entity request without an explicit entity list (default would be all entities → ask which one).
- Window wider than the skill's default (trailing 12 vs. single-month → ask).
- Large-tier workspace (>5 entities, or >300 tasks expected for the period).
- Account count expected to exceed the materiality gate's typical N (>100 leaves).

When any signal triggers, present concrete options and the projected cost:

> "This will pull 12 months of transactions across 5 entities (~60 API calls, est. 4–8 min). Continue, or narrow scope?"
>
> Entity: <list> — pick one, or 'all' (default)
> Accounts: 'all that exceed materiality' (default), or pick specific accounts
> Materiality: small workspace $1K (default), medium $5K, large $10K, custom

Only proceed after the user confirms. This pattern catches expensive runs before the data is pulled — earlier than fail-fast (after pull) or materiality gate (after pull + parse).

### Session-level cache for cold-start calls

`get_workspace_context`, `list_reports`, and `list_financial_accounts` change rarely within a session and are expensive (60K+ chars each). Write the response to `outputs/.numeric_session_cache/{workspace_id}_{call}.json` after the first call and read from cache on subsequent calls in the same session. TTL ~24h. This benefits any user who runs more than one skill in a session.
### Subagent rule — do not read tool-result content

Subagents must NOT read or display the TSV/JSON content of any tool-result file they handle. Only `cp` the redirected file to the cache path, then `wc -l` (or equivalent) for the line count. After that, return the contracted JSON immediately. Reading the content into context costs ~50K tokens per drill that should not be paid.

### Streaming progress — per subagent return, not fixed cadence

Emit one line per subagent return: `Drilled <name> (<n>/<N>)`. Do not wait for fixed batches of N — subagents finish out of order, so cadence-based emits arrive in clumps. Per-return updates keep the user informed in real time.
