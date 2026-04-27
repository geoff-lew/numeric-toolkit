"""
Generate a Slack-ready close retro digest from metrics.json.

Organizes output around diagnostic questions in plain language.
Reads the question bank to determine which questions to answer.

Input: metrics.json, workspace name, period name
Output: saves digest.md to output_dir

Usage: python3 generate_digest.py <metrics.json> <workspace_name> <period_name> <output_dir>
"""
import json, sys, os


def fmt(val, suffix=""):
    """Format a numeric value for display, handling None."""
    if val is None:
        return "n/a"
    if isinstance(val, float):
        if val == int(val):
            return f"{int(val)}{suffix}"
        return f"{val}{suffix}"
    return f"{val}{suffix}"


def generate(metrics_file, workspace_name, period_name, output_dir):
    with open(metrics_file) as f:
        m = json.load(f)

    lines = []
    add = lines.append

    # --- Header ---
    add(f"*Close Retrospective — {workspace_name} {period_name}*\n")

    # --- Headline ---
    headline = build_headline(m)
    add(f"*Headline:* {headline}\n")

    # --- KPI Snapshot ---
    add("*Quick numbers:*")
    bs = m.get("by_status", {})
    total = m.get("tasks_sampled", 0)
    completed = bs.get("completed", 0)
    pct = round(completed / max(total, 1) * 100)
    add(f"• {completed} of {total} tasks fully complete ({pct}%)")
    add(f"• Median task turnaround: {fmt(m['turnaround']['overall']['median'], 'd')}")
    add(f"• Prep turnaround: {fmt(m['turnaround']['prep']['median'], 'd')} | Review turnaround: {fmt(m['turnaround']['review']['median'], 'd')}")
    add(f"• Handoff rate (prep done → review started): {fmt(m['handoff']['rate_pct'], '%')}")
    add(f"• Reopens: {m['reopens']['total_cycles']} total across {m['reopens']['high_friction_task_count']} high-friction tasks")
    add(f"• Tasks without any due date: {fmt(m['coverage']['no_due_date_pct'], '%')}")
    add(f"• Tasks reassigned: {fmt(m['churn']['pct'], '%')}")
    bl = m.get("back_loading", {})
    if bl.get("score_pct") is not None:
        add(f"• Back-loading score: {fmt(bl['score_pct'], '%')} of completions in the final quarter of the close window")
    lt = m.get("late_tasks", {})
    if lt.get("due_dated_completed", 0) > 0:
        add(f"• Late tasks: {lt['count']} of {lt['due_dated_completed']} due-dated tasks ({fmt(lt['pct'], '%')})")
    dd = m.get("due_date_drift", {})
    if dd.get("tasks_with_changes", 0) > 0:
        add(f"• Due dates moved mid-close: {dd['tasks_with_changes']} tasks ({fmt(dd['pct'], '%')})")
    add("")

    # --- Pace & Timing ---
    add("*How's the pace?*")
    ft = m["first_touch"]
    add(f"After assignment, the typical task gets its first touch in {fmt(ft['median'], ' days')}. "
        f"{fmt(ft['zero_activity_pct'], '%')} of assigned tasks have had zero activity (dormant).")
    ta = m["turnaround"]["overall"]
    add(f"From assignment to completion, median turnaround is {fmt(ta['median'], ' days')} "
        f"(slowest 10% take {fmt(ta['p90'], '+ days')}).")
    bl = m.get("back_loading", {})
    if bl.get("score_pct") is not None:
        if bl["score_pct"] > 50:
            add(f"The close was back-loaded — {fmt(bl['score_pct'], '%')} of task completions landed in the final quarter of the window.")
        elif bl["score_pct"] < 30:
            add(f"Work was well-distributed across the close window ({fmt(bl['score_pct'], '%')} in the final quarter).")
        else:
            add(f"Back-loading score: {fmt(bl['score_pct'], '%')} of completions in the final quarter — moderate.")
        if bl.get("peak_day"):
            add(f"Busiest day: {bl['peak_day']} with {bl['peak_day_count']} completions. "
                f"{bl.get('quiet_days', 0)} days had zero completions.")
    # Slowest tasks
    slowest = m.get("slowest_tasks", [])
    if slowest:
        add(f"Slowest tasks (assignment to completion):")
        for i, st in enumerate(slowest[:5], 1):
            add(f"  {i}. {st['name']} — {fmt(st['days'], 'd')} ({st['assignee']}, {st['task_type']})")
    add("")

    # --- Review Quality ---
    add("*Is the review process working?*")
    ho = m["handoff"]
    add(f"{ho['prep_complete']} tasks have prep done. Of those, {ho['review_started']} have moved to review "
        f"({fmt(ho['rate_pct'], '%')} handoff rate).")
    rp = m["reopens"]
    if rp["total_cycles"] == 0:
        add("No tasks were sent back for rework — clean review cycle.")
    else:
        add(f"{rp['total_cycles']} tasks were sent back for rework. "
            f"When that happened, the rework cycle took a median of {fmt(rp['median_cycle_days'], ' days')} "
            f"(worst case: {fmt(rp['max_cycle_days'], ' days')}).")
        if rp["high_friction_task_count"] > 0:
            add(f"{rp['high_friction_task_count']} tasks had 2+ rounds of back-and-forth — worth investigating.")
    sr = m["coverage"]["self_review_count"]
    if sr > 0:
        add(f"{sr} tasks have the same person as preparer and reviewer (self-review).")
    add("")

    # --- Late tasks ---
    lt = m.get("late_tasks", {})
    if lt.get("due_dated_completed", 0) > 0:
        add("*Are tasks getting done on time?*")
        if lt["count"] == 0:
            add(f"All {lt['due_dated_completed']} due-dated tasks were completed on time.")
        else:
            add(f"{lt['count']} of {lt['due_dated_completed']} due-dated tasks were completed late ({fmt(lt['pct'], '%')}), "
                f"averaging {fmt(lt['avg_days_late'], ' days')} past due.")
            worst = lt.get("worst", [])
            if worst:
                add("Latest tasks:")
                for i, w in enumerate(worst[:5], 1):
                    add(f"  {i}. {w['name']} — {fmt(w['days_late'], 'd')} late ({w['assignee']}, due {w['due']})")
        # Due date drift
        dd = m.get("due_date_drift", {})
        if dd.get("tasks_with_changes", 0) > 0:
            add(f"{dd['tasks_with_changes']} tasks had their due date changed mid-close ({fmt(dd['pct'], '%')}).")
            if dd.get("unstable_tasks", 0) > 0:
                add(f"{dd['unstable_tasks']} tasks had 3+ date changes — the close calendar isn't holding for these.")
        add("")

    # --- Per-person rework ---
    users = m.get("per_user", [])
    rework_users = [u for u in users if u.get("reopens_caused", 0) > 0 or u.get("reopens_received", 0) > 0]
    if rework_users:
        add("*Who's involved in rework?*")
        for u in sorted(rework_users, key=lambda x: -(x["reopens_caused"] + x["reopens_received"])):
            parts = []
            if u["reopens_caused"] > 0:
                parts.append(f"sent back {u['reopens_caused']} tasks as reviewer")
            if u["reopens_received"] > 0:
                parts.append(f"had {u['reopens_received']} tasks sent back as preparer")
            add(f"• {u['name']}: {', '.join(parts)}")
        add("")

    # --- Workload ---
    add("*Is work spread evenly?*")
    conc = m["concentration"]
    if conc["top3_share_pct"] is not None:
        add(f"Top 3 people handle {fmt(conc['top3_share_pct'], '%')} of all tasks across {conc['assignee_count']} team members.")
    if conc["top5_share_pct"] is not None:
        add(f"Top 5 handle {fmt(conc['top5_share_pct'], '%')}.")

    # Per-user highlights
    users = m.get("per_user", [])
    if users:
        most_loaded = max(users, key=lambda u: u["total_tasks"])
        add(f"Most loaded: {most_loaded['name']} with {most_loaded['total_tasks']} tasks "
            f"({fmt(most_loaded['completion_rate'], '%')} complete).")

        with_turnaround = [u for u in users if u["median_turnaround_days"] is not None and u["median_turnaround_days"] >= 0]
        if with_turnaround:
            fastest = min(with_turnaround, key=lambda u: u["median_turnaround_days"])
            slowest = max(with_turnaround, key=lambda u: u["median_turnaround_days"])
            if fastest["name"] != slowest["name"]:
                add(f"Fastest median turnaround: {fastest['name']} ({fmt(fastest['median_turnaround_days'], 'd')}). "
                    f"Slowest: {slowest['name']} ({fmt(slowest['median_turnaround_days'], 'd')}).")

        dormant_users = [u for u in users if u["dormant_tasks"] > 0]
        if dormant_users:
            dormant_users.sort(key=lambda u: -u["dormant_tasks"])
            top_dormant = dormant_users[0]
            add(f"{top_dormant['name']} has {top_dormant['dormant_tasks']} assigned tasks with no activity yet.")
    add("")

    # --- Coverage gaps ---
    cov = m["coverage"]
    gaps = []
    if cov["unassigned_prep"] > 0:
        gaps.append(f"{cov['unassigned_prep']} tasks have no preparer assigned")
    if cov["unassigned_review"] > 0:
        gaps.append(f"{cov['unassigned_review']} tasks have no reviewer assigned")
    if cov["no_due_date_pct"] > 10:
        gaps.append(f"{fmt(cov['no_due_date_pct'], '%')} of tasks have no due date")
    if m["churn"]["pct"] > 15:
        gaps.append(f"{fmt(m['churn']['pct'], '%')} of tasks were reassigned (may indicate unclear ownership)")

    if gaps:
        add("*Setup gaps:*")
        for g in gaps:
            add(f"• {g}")
        add("")

    # --- What went well / What to watch ---
    well, watch = build_takeaways(m)
    if well:
        add("*What went well:*")
        for w in well:
            add(f"• {w}")
        add("")
    if watch:
        add("*What to watch:*")
        for w in watch:
            add(f"• {w}")
        add("")

    # --- Suggested actions ---
    actions = build_actions(m)
    if actions:
        add("*Suggested actions:*")
        for a in actions:
            add(f"• {a}")
        add("")

    digest = "\n".join(lines)

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "digest.md")
    with open(out_path, "w") as f:
        f.write(digest)

    print(f"Digest written to {out_path} ({len(lines)} lines)")
    return digest


def build_headline(m):
    """One-sentence headline based on the data."""
    bs = m.get("by_status", {})
    total = m.get("tasks_sampled", 0)
    completed = bs.get("completed", 0)
    pct = round(completed / max(total, 1) * 100)
    reopens = m["reopens"]["total_cycles"]
    dormant_pct = m["first_touch"]["zero_activity_pct"]

    parts = []
    if pct >= 90:
        parts.append(f"{pct}% complete")
    elif pct >= 70:
        parts.append(f"{pct}% complete — getting there")
    else:
        parts.append(f"Only {pct}% complete so far")

    if reopens == 0:
        parts.append("clean review cycles")
    elif reopens > 10:
        parts.append(f"{reopens} rework cycles flagged")

    if dormant_pct > 20:
        parts.append(f"{fmt(dormant_pct, '%')} of tasks untouched")

    return ". ".join(parts) + "."


def build_takeaways(m):
    """Derive what went well and what to watch from the metrics."""
    well = []
    watch = []

    # Reopens
    if m["reopens"]["total_cycles"] == 0:
        well.append("Zero rework cycles — reviews are clean.")
    elif m["reopens"]["high_friction_task_count"] > 3:
        watch.append(f"{m['reopens']['high_friction_task_count']} tasks had repeated back-and-forth between preparer and reviewer.")

    # Handoff
    if m["handoff"]["rate_pct"] >= 90:
        well.append(f"Strong handoff rate — {fmt(m['handoff']['rate_pct'], '%')} of completed prep moved to review.")
    elif m["handoff"]["rate_pct"] < 60:
        watch.append(f"Only {fmt(m['handoff']['rate_pct'], '%')} of prep-complete tasks have started review.")

    # Dormant
    if m["first_touch"]["zero_activity_pct"] < 10:
        well.append("Almost all assigned tasks have been touched.")
    elif m["first_touch"]["zero_activity_pct"] > 25:
        watch.append(f"{fmt(m['first_touch']['zero_activity_pct'], '%')} of assigned tasks have had zero activity.")

    # Coverage
    if m["coverage"]["no_due_date_pct"] > 30:
        watch.append(f"{fmt(m['coverage']['no_due_date_pct'], '%')} of tasks have no due date — hard to track lateness.")

    # Self-review
    if m["coverage"]["self_review_count"] > 5:
        watch.append(f"{m['coverage']['self_review_count']} tasks have the same person preparing and reviewing.")

    # Concentration
    if m["concentration"]["top3_share_pct"] and m["concentration"]["top3_share_pct"] > 60:
        watch.append(f"Workload is concentrated — top 3 people own {fmt(m['concentration']['top3_share_pct'], '%')} of tasks.")

    # Back-loading
    bl = m.get("back_loading", {})
    if bl.get("score_pct") is not None:
        if bl["score_pct"] < 35:
            well.append(f"Work was spread across the close window (only {fmt(bl['score_pct'], '%')} in the final quarter).")
        elif bl["score_pct"] > 60:
            watch.append(f"Back-loaded close — {fmt(bl['score_pct'], '%')} of completions happened in the last quarter of the window.")

    # Late tasks
    lt = m.get("late_tasks", {})
    if lt.get("count", 0) == 0 and lt.get("due_dated_completed", 0) > 5:
        well.append("All due-dated tasks completed on time.")
    elif lt.get("pct", 0) > 30:
        watch.append(f"{fmt(lt['pct'], '%')} of due-dated tasks were late.")

    # Due date drift
    dd = m.get("due_date_drift", {})
    if dd.get("pct", 0) > 20:
        watch.append(f"{fmt(dd['pct'], '%')} of tasks had due dates moved mid-close — the close calendar may need tightening.")

    return well, watch


def build_actions(m):
    """Suggest 1-3 actionable next steps."""
    actions = []

    if m["first_touch"]["zero_activity_pct"] > 15:
        actions.append("Follow up on dormant tasks — some assignees may need a nudge or the tasks may need reassignment.")

    if m["coverage"]["no_due_date_pct"] > 20:
        actions.append("Add due dates to undated tasks so lateness becomes trackable.")

    if m["reopens"]["high_friction_task_count"] > 2:
        actions.append("Review the high-friction tasks to see if clearer prep instructions or templates would reduce rework.")

    if m["handoff"]["rate_pct"] < 70:
        actions.append("Check why prep-complete tasks aren't moving to review — may need reviewer nudges or clearer handoff process.")

    if m["coverage"]["self_review_count"] > 3:
        actions.append("Reassign reviewers on self-review tasks to ensure proper separation of duties.")

    bl = m.get("back_loading", {})
    if bl.get("score_pct") and bl["score_pct"] > 55:
        actions.append("Set earlier interim deadlines to spread work across the close window and reduce the end-of-period crunch.")

    dd = m.get("due_date_drift", {})
    if dd.get("unstable_tasks", 0) > 2:
        actions.append(f"Investigate the {dd['unstable_tasks']} tasks with 3+ due date changes — recurring instability suggests the original dates aren't realistic.")

    lt = m.get("late_tasks", {})
    if lt.get("worst"):
        # Check if late tasks cluster on one person
        late_assignees = {}
        for w in lt["worst"]:
            late_assignees[w["assignee"]] = late_assignees.get(w["assignee"], 0) + 1
        worst_assignee = max(late_assignees.items(), key=lambda x: x[1])
        if worst_assignee[1] >= 3:
            actions.append(f"{worst_assignee[0]} had {worst_assignee[1]} late tasks — may need workload relief or earlier start dates.")

    users = m.get("per_user", [])
    if users:
        most_loaded = max(users, key=lambda u: u["total_tasks"])
        avg = sum(u["total_tasks"] for u in users) / max(len(users), 1)
        if most_loaded["total_tasks"] > avg * 2:
            actions.append(f"Consider redistributing work from {most_loaded['name']} who has {most_loaded['total_tasks']} tasks (team average: {int(avg)}).")

    return actions[:3]  # Cap at 3


if __name__ == "__main__":
    generate(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
