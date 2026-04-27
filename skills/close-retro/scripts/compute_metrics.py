"""
Compute all close retro metrics from parsed tasks and events.

Input: tasks.json, events.json, period start date (YYYY-MM-DD)
Output: saves metrics.json to output_dir

Usage: python3 compute_metrics.py <tasks.json> <events.json> <period_start> <output_dir>
"""
import json, sys, os
from datetime import datetime, timezone
from collections import defaultdict
import statistics


def days_between(iso_a, iso_b):
    """Days between two ISO timestamps or date strings."""
    def to_dt(s):
        s = s.replace("Z", "+00:00")
        if "T" in s:
            return datetime.fromisoformat(s)
        return datetime.fromisoformat(s + "T00:00:00+00:00")
    return (to_dt(iso_b) - to_dt(iso_a)).total_seconds() / 86400


def median_safe(lst):
    return round(statistics.median(lst), 1) if lst else None


def mean_safe(lst):
    return round(statistics.mean(lst), 1) if lst else None


def p90_safe(lst):
    if not lst:
        return None
    lst_sorted = sorted(lst)
    idx = int(len(lst_sorted) * 0.9)
    return round(lst_sorted[min(idx, len(lst_sorted) - 1)], 1)


def compute(tasks_file, events_file, period_start, output_dir):
    with open(tasks_file) as f:
        td = json.load(f)
    with open(events_file) as f:
        events = json.load(f)

    tasks = td["tasks"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Index events by task_id
    by_task = defaultdict(list)
    for e in events:
        by_task[e["task_id"]].append(e)

    # --- 1. Turnaround: assignment to completion ---
    turnaround_all = []
    turnaround_prep = []
    turnaround_review = []

    for task_id, tevs in by_task.items():
        submits = [e for e in tevs if e["action_key"] == "submit_task"]
        assigns = [e for e in tevs if e["action_key"] == "assign_task"]
        if not submits or not assigns:
            continue
        first_assign = min(assigns, key=lambda x: x["occurred_at"])
        for sub in submits:
            d = days_between(first_assign["occurred_at"], sub["occurred_at"])
            if d < 0:
                continue  # assignment happened after submit (data quirk)
            turnaround_all.append(d)
            role = sub.get("outputs", {}).get("role", "")
            if role == "ASSIGNEE":
                turnaround_prep.append(d)
            elif role in ("REVIEWER", "SECOND_REVIEWER"):
                turnaround_review.append(d)

    turnaround = {
        "overall": {"median": median_safe(turnaround_all), "mean": mean_safe(turnaround_all),
                     "p90": p90_safe(turnaround_all), "n": len(turnaround_all)},
        "prep": {"median": median_safe(turnaround_prep), "n": len(turnaround_prep)},
        "review": {"median": median_safe(turnaround_review), "n": len(turnaround_review)},
    }

    # --- 2. Handoff rate ---
    prep_done = [t for t in tasks if t.get("prep_status") == "COMPLETE"]
    review_started = [t for t in prep_done
                      if t.get("review_status") in ("COMPLETE",)
                      or any(e["action_key"] == "submit_task"
                             and e.get("outputs", {}).get("role") == "REVIEWER"
                             for e in by_task.get(t.get("key_id", ""), []))]
    handoff = {
        "prep_complete": len(prep_done),
        "review_started": len(review_started),
        "rate_pct": round(len(review_started) / max(len(prep_done), 1) * 100, 1),
    }

    # --- 3. First-touch latency ---
    first_touch_days = []
    zero_activity_count = 0
    tasks_with_assigns = 0
    for task_id, tevs in by_task.items():
        assigns = [e for e in tevs if e["action_key"] == "assign_task"]
        non_assigns = [e for e in tevs if e["action_key"] not in ("assign_task", "unassign_task", "remove_assignees")]
        if not assigns:
            continue
        tasks_with_assigns += 1
        first_assign = min(assigns, key=lambda x: x["occurred_at"])
        if not non_assigns:
            zero_activity_count += 1
            continue
        first_action = min(non_assigns, key=lambda x: x["occurred_at"])
        d = days_between(first_assign["occurred_at"], first_action["occurred_at"])
        if d >= 0:
            first_touch_days.append(d)

    first_touch = {
        "median": median_safe(first_touch_days),
        "p90": p90_safe(first_touch_days),
        "zero_activity_count": zero_activity_count,
        "zero_activity_pct": round(zero_activity_count / max(tasks_with_assigns, 1) * 100, 1),
    }

    # --- 4. Reassignment churn ---
    reassigned_count = 0
    changes_per_task = []
    for task_id, tevs in by_task.items():
        assigns = [e for e in tevs if e["action_key"] == "assign_task"]
        unique_users = set()
        for a in assigns:
            uid = a.get("outputs", {}).get("assigned", "")
            if uid:
                unique_users.add(uid)
        if len(unique_users) > 1:
            reassigned_count += 1
            changes_per_task.append(len(assigns))

    churn = {
        "tasks_reassigned": reassigned_count,
        "pct": round(reassigned_count / max(len(by_task), 1) * 100, 1),
        "median_changes": median_safe(changes_per_task),
    }

    # --- 5. Reopen cycles ---
    reopens_by_task = defaultdict(int)
    total_reopens = 0
    reopen_cycle_days = []
    for task_id, tevs in by_task.items():
        sorted_tevs = sorted(tevs, key=lambda x: x["occurred_at"])
        reopens = [e for e in sorted_tevs if e["action_key"] == "unsubmit_task"]
        reopens_by_task[task_id] = len(reopens)
        total_reopens += len(reopens)
        for reopen in reopens:
            # Find next submit after this reopen
            later_submits = [e for e in sorted_tevs
                             if e["action_key"] == "submit_task"
                             and e["occurred_at"] > reopen["occurred_at"]]
            if later_submits:
                d = days_between(reopen["occurred_at"], later_submits[0]["occurred_at"])
                reopen_cycle_days.append(d)

    high_friction = [(tid, cnt) for tid, cnt in reopens_by_task.items() if cnt >= 2]
    reopens = {
        "total_cycles": total_reopens,
        "median_cycle_days": median_safe(reopen_cycle_days),
        "max_cycle_days": round(max(reopen_cycle_days), 1) if reopen_cycle_days else 0,
        "high_friction_task_count": len(high_friction),
    }

    # --- 6. Back-loading score ---
    # What % of completions happened in the final 25% of the close window?
    submit_events = [e for e in events if e["action_key"] == "submit_task"]
    if submit_events:
        all_dates = [e["occurred_at"] for e in submit_events]
        first_submit = min(all_dates)
        last_submit = max(all_dates)
        window_days = days_between(first_submit, last_submit)
        if window_days > 0:
            cutoff_75 = days_between(first_submit, first_submit) + window_days * 0.75
            late_quarter = sum(1 for e in submit_events
                               if days_between(first_submit, e["occurred_at"]) >= cutoff_75)
            back_loading_pct = round(late_quarter / len(submit_events) * 100, 1)
        else:
            back_loading_pct = 0.0
        # Completions by day
        by_day = defaultdict(int)
        for e in submit_events:
            day = e["occurred_at"][:10]
            by_day[day] += 1
        peak_day = max(by_day.items(), key=lambda x: x[1])
        quiet_days = 0
        if window_days > 1:
            from datetime import timedelta
            start_dt = datetime.fromisoformat(first_submit[:10])
            end_dt = datetime.fromisoformat(last_submit[:10])
            d = start_dt
            while d <= end_dt:
                if d.strftime("%Y-%m-%d") not in by_day:
                    quiet_days += 1
                d += timedelta(days=1)
    else:
        back_loading_pct = None
        peak_day = (None, 0)
        quiet_days = 0

    back_loading = {
        "score_pct": back_loading_pct,
        "peak_day": peak_day[0],
        "peak_day_count": peak_day[1],
        "quiet_days": quiet_days,
    }

    # --- 7. Late tasks (completed after due date) ---
    # Build a task lookup by key_id for matching events to task metadata
    task_by_key = {}
    for t in tasks:
        kid = t.get("key_id", "")
        if kid:
            task_by_key[kid] = t

    late_tasks_list = []
    on_time_count = 0
    due_dated_completed = 0
    for task_id, tevs in by_task.items():
        task_meta = task_by_key.get(task_id)
        if not task_meta:
            continue
        submits = [e for e in tevs if e["action_key"] == "submit_task"]
        if not submits:
            continue
        last_submit = max(submits, key=lambda x: x["occurred_at"])
        submit_date = last_submit["occurred_at"][:10]

        # Check prep due
        prep_due = task_meta.get("prep_due", "")
        review_due = task_meta.get("review_due", "")
        due = prep_due or review_due
        if not due:
            continue
        due_dated_completed += 1
        days_late = days_between(due, submit_date)
        if days_late > 0:
            late_tasks_list.append({
                "name": task_meta.get("name", task_id),
                "assignee": task_meta.get("prep_assignee", "unknown"),
                "due": due,
                "completed": submit_date,
                "days_late": round(days_late, 1),
            })
        else:
            on_time_count += 1

    late_tasks_list.sort(key=lambda x: -x["days_late"])
    late_pct = round(len(late_tasks_list) / max(due_dated_completed, 1) * 100, 1)

    late_tasks = {
        "count": len(late_tasks_list),
        "pct": late_pct,
        "due_dated_completed": due_dated_completed,
        "on_time_count": on_time_count,
        "avg_days_late": mean_safe([t["days_late"] for t in late_tasks_list]),
        "worst": late_tasks_list[:10],  # Top 10 latest
    }

    # --- 8. Due date drift (edit_target_date events) ---
    date_change_tasks = defaultdict(int)
    for e in events:
        if e["action_key"] == "edit_target_date":
            date_change_tasks[e["task_id"]] += 1
    tasks_with_date_changes = len(date_change_tasks)
    unstable_tasks = sum(1 for cnt in date_change_tasks.values() if cnt >= 3)
    drift_pct = round(tasks_with_date_changes / max(len(tasks), 1) * 100, 1)

    due_date_drift = {
        "tasks_with_changes": tasks_with_date_changes,
        "pct": drift_pct,
        "unstable_tasks": unstable_tasks,  # 3+ changes
    }

    # --- 9. Slowest tasks by name ---
    task_turnarounds = []
    for task_id, tevs in by_task.items():
        submits = [e for e in tevs if e["action_key"] == "submit_task"]
        assigns = [e for e in tevs if e["action_key"] == "assign_task"]
        if not submits or not assigns:
            continue
        first_assign = min(assigns, key=lambda x: x["occurred_at"])
        last_submit = max(submits, key=lambda x: x["occurred_at"])
        d = days_between(first_assign["occurred_at"], last_submit["occurred_at"])
        if d < 0:
            continue
        task_meta = task_by_key.get(task_id, {})
        task_turnarounds.append({
            "name": task_meta.get("name", task_id),
            "assignee": task_meta.get("prep_assignee", "unknown"),
            "task_type": task_meta.get("task_type", "unknown"),
            "days": round(d, 1),
        })
    task_turnarounds.sort(key=lambda x: -x["days"])
    slowest_tasks = task_turnarounds[:5]

    # --- 10. Due date coverage ---
    unassigned_prep = sum(1 for t in tasks if not t.get("prep_assignee"))
    unassigned_review = sum(1 for t in tasks if not t.get("review_assignee"))
    self_review = sum(1 for t in tasks
                      if t.get("prep_assignee") and t.get("prep_assignee") == t.get("review_assignee"))
    coverage = {
        "no_due_date_pct": round(td["due_date_coverage"]["tasks_without_any_due"] / max(len(tasks), 1) * 100, 1),
        "unassigned_prep": unassigned_prep,
        "unassigned_review": unassigned_review,
        "self_review_count": self_review,
    }

    # --- 7. Workload concentration ---
    totals = []
    for name, info in td["assignees"].items():
        totals.append(info["prep_assigned"] + info["review_assigned"])
    totals.sort(reverse=True)
    total_all = sum(totals)
    top3_share = round(sum(totals[:3]) / max(total_all, 1) * 100, 1) if len(totals) >= 3 else None
    top5_share = round(sum(totals[:5]) / max(total_all, 1) * 100, 1) if len(totals) >= 5 else None

    concentration = {
        "assignee_count": len(td["assignees"]),
        "top3_share_pct": top3_share,
        "top5_share_pct": top5_share,
    }

    # --- 8. Per-user metrics ---
    per_user = []
    for name, info in td["assignees"].items():
        total = info["prep_assigned"] + info["review_assigned"]
        complete = info["prep_complete"] + info["review_complete"]
        # Find turnaround from events (need to match user name to events)
        user_turnarounds = []
        for task_id, tevs in by_task.items():
            submits = [e for e in tevs if e["action_key"] == "submit_task" and e["by_user"] == name]
            assigns = [e for e in tevs if e["action_key"] == "assign_task"]
            if submits and assigns:
                first_a = min(assigns, key=lambda x: x["occurred_at"])
                for s in submits:
                    d = days_between(first_a["occurred_at"], s["occurred_at"])
                    if d >= 0:
                        user_turnarounds.append(d)
        # Reopens
        user_reopens_recv = 0
        user_reopens_caused = 0
        for task_id, tevs in by_task.items():
            for e in tevs:
                if e["action_key"] == "unsubmit_task":
                    # Check if this user is the preparer (received) or the reopener (caused)
                    if e["by_user"] == name:
                        user_reopens_caused += 1
                    # Count received if any assign to this user on this task
                    task_assigns = [a for a in tevs
                                    if a["action_key"] == "assign_task"
                                    and a.get("outputs", {}).get("assigned") == name]
                    if task_assigns:
                        user_reopens_recv += 1

        # Dormant tasks
        dormant = 0
        for task_id, tevs in by_task.items():
            assigns_to_user = [e for e in tevs
                               if e["action_key"] == "assign_task"
                               and e.get("outputs", {}).get("assigned") == name]
            if not assigns_to_user:
                continue
            non_assigns = [e for e in tevs if e["action_key"] not in ("assign_task", "unassign_task", "remove_assignees")]
            if not non_assigns:
                dormant += 1

        per_user.append({
            "name": name,
            "total_tasks": total,
            "completion_rate": round(complete / max(total, 1) * 100, 1),
            "median_turnaround_days": median_safe(user_turnarounds),
            "reopens_received": user_reopens_recv,
            "reopens_caused": user_reopens_caused,
            "dormant_tasks": dormant,
        })

    per_user.sort(key=lambda x: -x["total_tasks"])

    metrics = {
        "period_start": period_start,
        "total_tasks_in_period": td["total_in_period"],
        "tasks_sampled": td["total_parsed"],
        "by_status": td["by_status"],
        "by_task_type": td["by_task_type"],
        "turnaround": turnaround,
        "handoff": handoff,
        "first_touch": first_touch,
        "churn": churn,
        "reopens": reopens,
        "back_loading": back_loading,
        "late_tasks": late_tasks,
        "due_date_drift": due_date_drift,
        "slowest_tasks": slowest_tasks,
        "coverage": coverage,
        "concentration": concentration,
        "per_user": per_user,
    }

    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"\nMetrics computed for {td['total_parsed']} tasks, {len(events)} events")
    print(f"  Turnaround: median {turnaround['overall']['median']}d (n={turnaround['overall']['n']})")
    print(f"  Prep: {turnaround['prep']['median']}d | Review: {turnaround['review']['median']}d")
    print(f"  Handoff: {handoff['rate_pct']}% ({handoff['prep_complete']} prep done, {handoff['review_started']} to review)")
    print(f"  First-touch: median {first_touch['median']}d, {first_touch['zero_activity_pct']}% dormant")
    print(f"  Churn: {churn['pct']}% reassigned")
    print(f"  Reopens: {reopens['total_cycles']} total, {reopens['high_friction_task_count']} high-friction tasks")
    return metrics


if __name__ == "__main__":
    compute(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
