#!/usr/bin/env python3
"""
aggregate_workspace.py — produce a per-workspace dashboard summary.

Numeric `list_tasks` TSV has this shape:
    <N> tasks                                                       (count line)
    name  task_type  key_id  key_type  report_id  prep_assignee
        prep_status  prep_due  review_assignee  review_status
        review_due  url                                              (header)
    <data rows>

A task is considered "complete" when both prep_status and review_status are
COMPLETE (or review is empty/IMMATERIAL with prep COMPLETE). It is "late"
when (a) it is not complete and (b) any non-empty due date is before as_of.

Outputs a small JSON the parent merges into the cross-workspace dashboard.

Usage:
    python aggregate_workspace.py --tasks tasks.tsv [--events events.json]
        --out summary.json --workspace-name "Acme US"
        [--workspace-id wks_...] [--period-id per_...]
        [--as-of YYYY-MM-DD] [--sole-reviewer-threshold 50]
"""
import argparse
import csv
import io
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


COMPLETE_STATUSES = {"COMPLETE", "IMMATERIAL", "SKIPPED"}


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s.split("T")[0].split(" ")[0], "%Y-%m-%d")
        except ValueError:
            continue
        except Exception:
            continue
    return None


def is_complete(prep_status, review_status):
    """A task is complete when prep is done AND (no reviewer OR reviewer is done)."""
    prep = (prep_status or "").strip().upper()
    review = (review_status or "").strip().upper()
    if prep not in COMPLETE_STATUSES:
        return False
    # If no reviewer status field, just prep
    if not review or review in COMPLETE_STATUSES:
        return True
    return False


def open_tasks_tsv(path):
    """Open a Numeric tasks TSV, skipping a leading 'N tasks' count line if present."""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    # Skip the leading count line ("1378 tasks", "0 tasks", etc.)
    if lines and lines[0].strip().endswith("tasks") and "\t" not in lines[0]:
        lines = lines[1:]
    return io.StringIO("\n".join(lines))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", required=True)
    p.add_argument("--events", required=False, help="Parsed events JSON (optional)")
    p.add_argument("--out", required=True)
    p.add_argument("--workspace-name", required=True)
    p.add_argument("--workspace-id", default="")
    p.add_argument("--period-id", default="")
    p.add_argument("--sole-reviewer-threshold", type=int, default=50)
    p.add_argument("--as-of", default="", help="As-of date YYYY-MM-DD for late computation")
    args = p.parse_args()

    tasks_path = Path(args.tasks)
    if not tasks_path.exists():
        print(f"ERROR: tasks file not found: {tasks_path}", file=sys.stderr)
        sys.exit(2)

    as_of = parse_date(args.as_of) if args.as_of else datetime.utcnow()

    type_counts = Counter()
    prep_status_counts = Counter()
    review_status_counts = Counter()
    completed = 0
    late_count = 0
    late_by_assignee = Counter()
    reviewer_load = Counter()
    preparer_load = Counter()
    total = 0

    handle = open_tasks_tsv(tasks_path)
    reader = csv.DictReader(handle, delimiter="\t")
    if not reader.fieldnames:
        print("ERROR: empty tasks TSV (no header found after count line)", file=sys.stderr)
        sys.exit(2)

    for row in reader:
        total += 1
        prep_status = (row.get("prep_status") or "").strip()
        review_status = (row.get("review_status") or "").strip()
        prep_assignee = (row.get("prep_assignee") or "").strip()
        review_assignee = (row.get("review_assignee") or "").strip()
        task_type = (row.get("task_type") or "").strip()

        type_counts[task_type or "unknown"] += 1
        prep_status_counts[prep_status or "unknown"] += 1
        review_status_counts[review_status or "(none)"] += 1
        if prep_assignee:
            preparer_load[prep_assignee] += 1
        if review_assignee:
            reviewer_load[review_assignee] += 1

        if is_complete(prep_status, review_status):
            completed += 1
            continue

        # Late: any non-empty due date in the past, task not complete
        prep_due = parse_date(row.get("prep_due"))
        review_due = parse_date(row.get("review_due"))
        is_late = False
        if prep_due and prep_due < as_of and prep_status not in COMPLETE_STATUSES:
            is_late = True
        if review_due and review_due < as_of and review_status not in COMPLETE_STATUSES and review_status:
            is_late = True
        if is_late:
            late_count += 1
            owner = prep_assignee if prep_status not in COMPLETE_STATUSES else review_assignee
            if owner:
                late_by_assignee[owner] += 1

    sole_reviewers = [{"reviewer": r, "task_count": c}
                      for r, c in reviewer_load.most_common()
                      if c >= args.sole_reviewer_threshold]

    completion_pct = round(completed / total * 100, 1) if total else 0.0

    out = {
        "workspace_name": args.workspace_name,
        "workspace_id": args.workspace_id,
        "period_id": args.period_id,
        "as_of": as_of.strftime("%Y-%m-%d"),
        "total_tasks": total,
        "completed_tasks": completed,
        "completion_pct": completion_pct,
        "type_counts": dict(type_counts),
        "prep_status_counts": dict(prep_status_counts),
        "review_status_counts": dict(review_status_counts),
        "late_count": late_count,
        "late_by_assignee": dict(late_by_assignee.most_common(20)),
        "top_preparers": dict(preparer_load.most_common(20)),
        "top_reviewers": dict(reviewer_load.most_common(20)),
        "sole_reviewer_warnings": sole_reviewers,
    }

    if args.events and Path(args.events).exists():
        try:
            events = json.loads(Path(args.events).read_text())
            if isinstance(events, list):
                out["event_count"] = len(events)
        except json.JSONDecodeError:
            pass

    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"Wrote summary for {args.workspace_name}: "
          f"{total} tasks, {completed} complete ({completion_pct}%), {late_count} late → {args.out}")


if __name__ == "__main__":
    main()
