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
