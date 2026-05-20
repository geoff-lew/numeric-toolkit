#!/usr/bin/env python3
"""
Close Checklist Diagnostic Tool
Analyzes a Numeric workspace's close checklist and generates an HTML report.
"""

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


# ============================================================
# Data Models
# ============================================================

@dataclass
class CompanyProfile:
    workspace_name: str = ""
    workspace_key: str = ""
    period_slug: str = ""
    period_start: str = ""
    period_end: str = ""
    license_tier: str = ""

    # Auto-detected
    team_size: int = 0
    team_tier: str = ""  # solo / small / mid / large
    active_users: list = field(default_factory=list)
    inactive_users: list = field(default_factory=list)
    entity_count: int = 0
    entities: list = field(default_factory=list)
    multi_currency: bool = False
    currencies: list = field(default_factory=list)
    close_window_days: int = 0
    close_start: str = ""
    close_end: str = ""
    tag_groups: list = field(default_factory=list)
    holidays: list = field(default_factory=list)
    has_audit_tag: bool = False
    has_non_close_exclusion: bool = False

    # From intake
    industry: str = ""
    audit_requirement: str = ""  # big4 / regional / none
    target_close_days: int = 0
    current_close_days: int = 0  # self-reported by controller
    outsourced: dict = field(default_factory=dict)
    secondary_book: bool = False
    from_csv: bool = False  # True when data comes from CSV export (some analyzers N/A)


@dataclass
class Task:
    name: str = ""
    task_type: str = ""  # custom, rec_prepare_account, flux, journal_entry
    key_id: str = ""
    key_type: str = ""
    report_id: str = ""
    prep_assignee: str = ""
    prep_status: str = ""
    prep_due: str = ""
    review_assignee: str = ""
    review_status: str = ""
    review_due: str = ""
    url: str = ""
    description: str = ""
    properties: dict = field(default_factory=dict)
    _prep_submitted_at: str = ""  # For late submission analysis
    _review_submitted_at: str = ""


@dataclass
class Finding:
    dimension: str  # accountability, controls, completeness, structure, properties, timeline, hygiene, journal_entries, dependencies
    severity: str  # critical, warning, info
    title: str
    detail: str
    action: str
    tier: str  # fix_now, fix_this_close, fix_this_quarter
    affected_tasks: list = field(default_factory=list)  # list of task names for drill-down
    affected_task_urls: dict = field(default_factory=dict)  # task name → deep link URL


# ============================================================
# Data Parsing
# ============================================================

def parse_workspace_context(ctx: dict) -> CompanyProfile:
    profile = CompanyProfile()
    profile.workspace_key = ctx.get("workspaceKey", "")
    profile.license_tier = ctx.get("license", "")

    # Users
    users = ctx.get("users", [])
    profile.active_users = [u for u in users if u.get("active")]
    profile.inactive_users = [u for u in users if not u.get("active")]

    # Entities
    entities = ctx.get("entities", [])
    profile.entity_count = len(entities)
    profile.entities = [e.get("name", "") for e in entities]
    currencies = list(set(e.get("base_currency", "") for e in entities))
    profile.currencies = currencies
    profile.multi_currency = len(currencies) > 1

    # Periods — find most recent closed
    periods = ctx.get("periods", [])
    closed = [p for p in periods if p.get("status") == "closed"]
    if closed:
        latest = sorted(closed, key=lambda p: (p["end"]["year"], p["end"]["month"]))[-1]
        profile.period_slug = latest.get("slug", "")
        s = latest.get("start", {})
        e = latest.get("end", {})
        profile.period_start = f"{s.get('year', '')}-{s.get('month', ''):02d}-{s.get('day', ''):02d}"
        profile.period_end = f"{e.get('year', '')}-{e.get('month', ''):02d}-{e.get('day', ''):02d}"

    # Tag groups
    profile.tag_groups = ctx.get("tagGroups", [])
    for tg in profile.tag_groups:
        for opt in tg.get("options", []):
            if opt.get("name", "").lower() == "audit" and opt.get("exclude_from_progress"):
                profile.has_audit_tag = True
            if opt.get("exclude_from_progress") and "non" in opt.get("name", "").lower() and "close" in opt.get("name", "").lower():
                profile.has_non_close_exclusion = True

    # Holidays
    profile.holidays = ctx.get("holidays", [])

    return profile


def parse_tasks(tsv_text: str, profile: CompanyProfile) -> list:
    lines = tsv_text.strip().split("\n")
    if not lines:
        return []

    # First line might be "N tasks"
    start = 0
    if lines[0].endswith("tasks") or "tasks" in lines[0]:
        start = 1

    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), delimiter="\t")
    tasks = []
    assignees = set()

    for row in reader:
        t = Task()
        t.name = (row.get("name") or "")
        t.task_type = (row.get("task_type") or "")
        t.key_id = (row.get("key_id") or "")
        t.key_type = (row.get("key_type") or "")
        t.report_id = (row.get("report_id") or "")
        t.prep_assignee = (row.get("prep_assignee") or "").strip()
        t.prep_status = (row.get("prep_status") or "").strip()
        t.prep_due = (row.get("prep_due") or "").strip()
        t.review_assignee = (row.get("review_assignee") or "").strip()
        t.review_status = (row.get("review_status") or "").strip()
        t.review_due = (row.get("review_due") or "").strip()
        t.url = (row.get("url") or "")
        t.description = (row.get("description") or "").strip()

        # Remaining columns are properties
        known_cols = {"name", "task_type", "key_id", "key_type", "report_id",
                      "prep_assignee", "prep_status", "prep_due",
                      "review_assignee", "review_status", "review_due", "url", "description"}
        t.properties = {k: v.strip() if v else "" for k, v in row.items() if k not in known_cols and k}
        tasks.append(t)

        if t.prep_assignee:
            assignees.add(t.prep_assignee)
        if t.review_assignee:
            assignees.add(t.review_assignee)

    # Update profile with task-derived info
    profile.team_size = len(assignees)
    if profile.team_size <= 1:
        profile.team_tier = "solo"
    elif profile.team_size <= 3:
        profile.team_tier = "small"
    elif profile.team_size <= 7:
        profile.team_tier = "mid"
    else:
        profile.team_tier = "large"

    # Close window from due dates — exclude non-close tasks to avoid inflation
    # Build set of category names that are excluded from progress
    exclude_cats = set()
    for tg in profile.tag_groups:
        for opt in tg.get("options", []):
            if opt.get("exclude_from_progress"):
                exclude_cats.add(opt.get("name", "").strip().lower())

    close_tasks_for_window = []
    for t in tasks:
        if not t.prep_due:
            continue
        # Skip tasks in non-close categories
        cat = t.properties.get("Category", "").strip().lower()
        if cat and cat in exclude_cats:
            continue
        close_tasks_for_window.append(t)

    dues = [t.prep_due for t in close_tasks_for_window]
    if dues:
        sorted_dues = sorted(dues)
        profile.close_start = sorted_dues[0]
        profile.close_end = sorted_dues[-1]
        try:
            d1 = datetime.strptime(sorted_dues[0], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_dues[-1], "%Y-%m-%d")

            # Trim outliers: use 5th-95th percentile of due dates to avoid
            # single early/late tasks inflating the window
            if len(sorted_dues) >= 10:
                p5 = sorted_dues[len(sorted_dues) // 20]
                p95 = sorted_dues[-1 - len(sorted_dues) // 20]
                d1 = datetime.strptime(p5, "%Y-%m-%d")
                d2 = datetime.strptime(p95, "%Y-%m-%d")
                profile.close_start = p5
                profile.close_end = p95

            # Count business days
            bdays = 0
            current = d1
            while current <= d2:
                if current.weekday() < 5:
                    bdays += 1
                current += timedelta(days=1)
            profile.close_window_days = bdays
        except ValueError:
            profile.close_window_days = 0

    return tasks


def parse_csv_export(csv_path: str) -> tuple:
    """Parse a Numeric CSV checklist export into (CompanyProfile, list[Task]).

    CSV export columns:
    Name, Category, Entity(ies), [property columns...], Function, Close Task Classification,
    Preparer, Preparer Submitted At, Due, Reviewer, Reviewer Submitted At, Due, Status

    Returns a tuple of (profile, tasks) since CSV exports contain enough data
    to build a basic profile without needing workspace context from the API.
    """
    # Try multiple encodings — customer exports vary
    raw = None
    for enc in ("utf-8-sig", "utf-8", "latin-1", "cp1252"):
        try:
            with open(csv_path, encoding=enc) as f:
                raw = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if raw is None:
        with open(csv_path, encoding="latin-1", errors="replace") as f:
            raw = f.read()
    # Strip NUL bytes that can appear in Excel-exported CSVs
    raw = raw.replace("\x00", "")
    reader = csv.DictReader(io.StringIO(raw))
    rows = list(reader)

    if not rows:
        return CompanyProfile(), []

    headers = list(rows[0].keys())

    # Identify which columns are "Due" — there are two: prep due and review due
    due_indices = [i for i, h in enumerate(headers) if h == "Due"]
    prep_due_idx = due_indices[0] if len(due_indices) >= 1 else None
    review_due_idx = due_indices[1] if len(due_indices) >= 2 else None

    # Convert rows to list-of-values for positional access on duplicate "Due" columns
    # Re-read with raw csv to handle duplicate column names
    with open(csv_path, encoding="utf-8-sig") as f:
        raw_reader = csv.reader(f)
        raw_headers = next(raw_reader)
        raw_rows = list(raw_reader)

    # Find column indices
    col_map = {}
    for i, h in enumerate(raw_headers):
        key = h.strip().strip('"')
        if key == "Due":
            if "prep_due" not in col_map:
                col_map["prep_due"] = i
            else:
                col_map["review_due"] = i
        elif key == "Name":
            col_map["name"] = i
        elif key == "Category":
            col_map["category"] = i
        elif key == "Entity(ies)":
            col_map["entity"] = i
        elif key == "Function":
            col_map["function"] = i
        elif key == "Close Task Classification":
            col_map["classification"] = i
        elif key == "Preparer":
            col_map["preparer"] = i
        elif key == "Preparer Submitted At":
            col_map["prep_submitted"] = i
        elif key == "Reviewer":
            col_map["reviewer"] = i
        elif key == "Reviewer Submitted At":
            col_map["review_submitted"] = i
        elif key == "Status":
            col_map["status"] = i
        else:
            # Additional property columns (e.g., "(Revenue Team) GL Account/Metric")
            col_map.setdefault("_properties", []).append((i, key))

    tasks = []
    assignees = set()
    entities = set()
    categories = set()
    # Track section headers (rows where Name matches a category and all other fields are Uncategorized/Unassigned)
    section_headers = set()

    for raw_row in raw_rows:
        if len(raw_row) < len(raw_headers):
            continue

        def get(key, default=""):
            idx = col_map.get(key)
            if idx is not None and idx < len(raw_row):
                return raw_row[idx].strip().strip('"')
            return default

        name = get("name")
        category = get("category")
        entity = get("entity")
        preparer = get("preparer")
        reviewer = get("reviewer")
        status = get("status")
        prep_due = get("prep_due")
        review_due = get("review_due")
        prep_submitted = get("prep_submitted")
        review_submitted = get("review_submitted")
        function_val = get("function")
        classification = get("classification")

        # Skip section header rows (category headers with no real data)
        if (preparer in ("Unassigned", "") and reviewer in ("Unassigned", "")
            and status in ("Unassigned", "") and not prep_due and not review_due
            and category == "Uncategorized"):
            section_headers.add(name)
            continue

        # Map status to Numeric's internal status format
        if status == "Completed":
            prep_status = "COMPLETE"
            review_status = "COMPLETE" if review_submitted else "PENDING"
        elif status == "Prepared":
            prep_status = "COMPLETE"
            review_status = "PENDING"
        elif status == "Assigned":
            prep_status = "PENDING"
            review_status = "PENDING"
        elif status == "Skipped":
            prep_status = "SKIPPED"
            review_status = "SKIPPED"
        else:
            prep_status = "PENDING"
            review_status = "PENDING"

        # Clean up assignees
        if preparer in ("Unassigned", ""):
            preparer = ""
        if reviewer in ("Unassigned", ""):
            reviewer = ""

        # Determine task type from Function column and name
        task_type = "custom"
        name_lower = name.lower()
        if function_val:
            func_lower = function_val.lower()
            if "journal entry" in func_lower:
                task_type = "journal_entry"
            elif "reconciliation" in func_lower or "rec" in func_lower:
                task_type = "rec_prepare_account"
            elif "flux" in func_lower:
                task_type = "flux"
        # Also infer from name if Function is just "Task"
        if task_type == "custom":
            if name_lower.startswith("reconcile ") or "reconciliation" in name_lower:
                task_type = "rec_prepare_account"
            elif any(kw in name_lower for kw in ["journal entry", " je ", "reclass"]):
                task_type = "journal_entry"

        # Parse date — CSV has "YYYY-MM-DD" format
        if prep_due and len(prep_due) >= 10:
            prep_due = prep_due[:10]
        if review_due and len(review_due) >= 10:
            review_due = review_due[:10]

        t = Task(
            name=name,
            task_type=task_type,
            key_type="custom",  # CSV exports don't include key_type
            prep_assignee=preparer,
            prep_status=prep_status,
            prep_due=prep_due,
            review_assignee=reviewer,
            review_status=review_status,
            review_due=review_due,
            description="(not available in CSV export)",  # Mark as unavailable, not empty
            properties={},
            _prep_submitted_at=prep_submitted or "",
            _review_submitted_at=review_submitted or "",
        )

        # Map CSV columns to properties
        if category and category != "Uncategorized":
            t.properties["Category"] = category
        if entity and entity != "Uncategorized":
            t.properties["Entity"] = entity
            entities.add(entity)
        if classification and classification != "Uncategorized":
            t.properties["Close Task Classification"] = classification
        # Additional property columns
        for prop_idx, prop_name in col_map.get("_properties", []):
            if prop_idx < len(raw_row):
                val = raw_row[prop_idx].strip().strip('"')
                if val and val != "Uncategorized":
                    t.properties[prop_name] = val

        tasks.append(t)
        if preparer:
            assignees.add(preparer)
        if reviewer:
            assignees.add(reviewer)
        if category and category != "Uncategorized":
            categories.add(category)

    # Build profile from CSV data
    profile = CompanyProfile()
    profile.from_csv = True
    profile.team_size = len(assignees)
    profile.active_users = [{"name": a, "active": True} for a in sorted(assignees)]
    profile.inactive_users = []
    profile.entity_count = len(entities)
    profile.entities = sorted(entities)

    # Detect multi-currency from entity names (heuristic — real detection needs API)
    profile.multi_currency = len(entities) > 1  # conservative assumption for multi-entity

    if profile.team_size <= 1:
        profile.team_tier = "solo"
    elif profile.team_size <= 3:
        profile.team_tier = "small"
    elif profile.team_size <= 7:
        profile.team_tier = "mid"
    else:
        profile.team_tier = "large"

    # Build synthetic tag groups from the categories and properties we found
    profile.tag_groups = []
    if categories:
        profile.tag_groups.append({
            "name": "Category",
            "is_required": False,
            "options": [{"name": c} for c in sorted(categories)],
        })
    if entities:
        profile.tag_groups.append({
            "name": "Entity",
            "is_required": False,
            "options": [{"name": e} for e in sorted(entities)],
        })
    # Check for Close Task Classification values
    classifications = set()
    for t in tasks:
        c = t.properties.get("Close Task Classification", "")
        if c:
            classifications.add(c)
    if classifications:
        profile.tag_groups.append({
            "name": "Close Task Classification",
            "is_required": False,
            "options": [{"name": c, "exclude_from_progress": "overview" in c.lower()} for c in sorted(classifications)],
        })

    # Close window from due dates
    dues = [t.prep_due for t in tasks if t.prep_due]
    if dues:
        sorted_dues = sorted(dues)
        profile.close_start = sorted_dues[0]
        profile.close_end = sorted_dues[-1]
        try:
            d1 = datetime.strptime(sorted_dues[0], "%Y-%m-%d")
            d2 = datetime.strptime(sorted_dues[-1], "%Y-%m-%d")
            bdays = 0
            current = d1
            while current <= d2:
                if current.weekday() < 5:
                    bdays += 1
                current += timedelta(days=1)
            profile.close_window_days = bdays
        except ValueError:
            profile.close_window_days = 0

    return profile, tasks


# ============================================================
# Universal Best Practices
# ============================================================

UNIVERSAL_ALWAYS = [
    {"name": "Bank reconciliation", "keywords": ["bank rec", "bank reconcil", "cash reconcil"], "category_hint": "cash"},
    {"name": "AP aging / review", "keywords": ["ap aging", "accounts payable aging", "ap review", "ap reconcil"], "category_hint": "payable"},
    {"name": "Payroll reconciliation", "keywords": ["payroll rec", "payroll reconcil", "payroll accru"], "category_hint": "payroll"},
    {"name": "Fixed asset depreciation", "keywords": ["depreciat", "fixed asset", "fa deprec"], "category_hint": "fixed asset"},
    {"name": "Accruals review", "keywords": ["accrual review", "accrued liab", "review accrual"], "category_hint": "accrual"},
    {"name": "Financial reporting / close package", "keywords": ["financial report", "close package", "financial statement", "reporting package"], "category_hint": "reporting"},
    {"name": "Management review / sign-off", "keywords": ["management review", "controller sign", "sign-off", "sign off", "controller review", "final review"], "category_hint": "reporting"},
    {"name": "Tax provision / sales tax", "keywords": ["tax provision", "sales tax", "tax accrual", "income tax"], "category_hint": "tax"},
]

UNIVERSAL_MULTI_ENTITY = [
    {"name": "Intercompany eliminations", "keywords": ["intercompany elim", "ic elim", "elimination", "intercompany reconcil"], "category_hint": "intercompany"},
    {"name": "Consolidation", "keywords": ["consolidat", "consol entry", "consol adjustment"], "category_hint": "reporting"},
]

UNIVERSAL_MULTI_CURRENCY = [
    {"name": "FX revaluation / remeasurement", "keywords": ["fx reval", "foreign currency", "fx adjust", "reval", "remeasur", "currency translat", "unrealized gain", "unrealized loss"], "category_hint": ""},
]

UNIVERSAL_AUDITED = [
    {"name": "Audit documentation / archival", "keywords": ["audit doc", "audit prep", "pbc", "audit archiv", "audit evidence"], "category_hint": "audit"},
]

UNIVERSAL_SAAS = [
    {"name": "Deferred revenue reconciliation", "keywords": ["deferred rev", "def rev", "deferred revenue rec"], "category_hint": "revenue"},
    {"name": "ASC 606 / revenue recognition review", "keywords": ["asc 606", "rev rec", "revenue recognition"], "category_hint": "revenue"},
]

UNIVERSAL_MANUFACTURING = [
    {"name": "Inventory valuation / count", "keywords": ["inventory val", "inventory count", "physical inventory", "inventory reconcil"], "category_hint": "inventory"},
    {"name": "COGS reconciliation", "keywords": ["cogs", "cost of goods", "cost of revenue"], "category_hint": ""},
    {"name": "WIP accounting", "keywords": ["wip", "work in progress", "work-in-progress"], "category_hint": "inventory"},
]

STRUCTURAL_BEST_PRACTICES = [
    {"name": "Pre-close tasks exist", "check": "pre_close", "description": "Tasks with due dates before or on month-end (system sync, cutoff notifications, department reminders)"},
    {"name": "Post-close / reporting phase exists", "check": "post_close", "description": "Tasks in the final days for financial reporting, close package delivery, and process improvement"},
    {"name": "Non-close tasks properly excluded", "check": "non_close_excluded", "description": "Non-close tasks (tax filings, compliance, board reporting) use exclude-from-progress tagging"},
]


def check_task_matches(tasks: list, keywords: list) -> bool:
    for t in tasks:
        name_lower = t.name.lower()
        desc_lower = t.description.lower() if t.description else ""
        combined = name_lower + " " + desc_lower
        for kw in keywords:
            if kw in combined:
                return True
    return False


# ============================================================
# Analyzers
# ============================================================

def analyze_accountability(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    # Unassigned tasks
    no_prep = [t for t in tasks if not t.prep_assignee]
    no_review = [t for t in tasks if not t.review_assignee]

    if no_prep:
        je_no_prep = [t for t in no_prep if t.task_type == "journal_entry"]
        rec_no_prep = [t for t in no_prep if t.task_type == "rec_prepare_account"]
        severity = "critical" if (profile.audit_requirement != "none" and (je_no_prep or rec_no_prep)) else "warning"
        detail_parts = [f"{len(no_prep)} of {len(tasks)} tasks have no preparer assigned."]
        if je_no_prep:
            detail_parts.append(f"{len(je_no_prep)} are journal entries.")
        if rec_no_prep:
            detail_parts.append(f"{len(rec_no_prep)} are reconciliations.")
        detail_parts.append("Well-run close processes assign a preparer to every task — it's the foundation of accountability during the close.")
        findings.append(Finding(
            dimension="accountability",
            severity=severity,
            title=f"{len(no_prep)} task{'s' if len(no_prep) != 1 else ''} {'have' if len(no_prep) != 1 else 'has'} no preparer",
            detail=" ".join(detail_parts),
            action="Assign a preparer to each unassigned task. Start with journal entries and reconciliations — those carry the most audit risk.",
            tier="fix_now",
            affected_tasks=[t.name for t in no_prep[:20]],
        ))

    # Inactive assignees
    inactive_names = {u["name"] for u in profile.inactive_users}
    inactive_prep = defaultdict(list)
    inactive_rev = defaultdict(list)
    for t in tasks:
        if t.prep_assignee in inactive_names:
            inactive_prep[t.prep_assignee].append(t)
        if t.review_assignee in inactive_names:
            inactive_rev[t.review_assignee].append(t)

    all_inactive = set(inactive_prep.keys()) | set(inactive_rev.keys())
    if all_inactive:
        details = []
        for name in sorted(all_inactive):
            pc = len(inactive_prep.get(name, []))
            rc = len(inactive_rev.get(name, []))
            parts = []
            if pc:
                parts.append(f"{pc} as preparer")
            if rc:
                parts.append(f"{rc} as reviewer")
            details.append(f"{name}: {', '.join(parts)}")
        findings.append(Finding(
            dimension="accountability",
            severity="critical",
            title=f"{sum(len(v) for v in inactive_prep.values()) + sum(len(v) for v in inactive_rev.values())} task{'s' if (sum(len(v) for v in inactive_prep.values()) + sum(len(v) for v in inactive_rev.values())) != 1 else ''} assigned to {len(all_inactive)} inactive user{'s' if len(all_inactive) > 1 else ''}",
            detail="These users are no longer active but still own tasks: " + "; ".join(details) + ". This is a common gap — when someone leaves or changes roles, their tasks often get orphaned.",
            action="Reassign these tasks to active team members. Sort by due date and tackle the ones due soonest first.",
            tier="fix_now"
        ))

    # Workload imbalance
    prep_counts = Counter(t.prep_assignee for t in tasks if t.prep_assignee)
    if len(prep_counts) >= 2:
        most = prep_counts.most_common(1)[0]
        least = prep_counts.most_common()[-1]
        ratio = most[1] / max(least[1], 1)
        pct = most[1] / len(tasks) * 100

        # Scale thresholds with team size — on a 2-person team, imbalance is expected
        warn_ratio = 5 if profile.team_tier in ("solo", "small") else 3
        crit_ratio = 8 if profile.team_tier in ("solo", "small") else 5

        if ratio > warn_ratio:
            severity = "critical" if ratio > crit_ratio else "warning"
            top3 = prep_counts.most_common(3)
            detail = f"{most[0]} owns {most[1]} tasks ({pct:.0f}% of total). "
            detail += "Top preparers: " + ", ".join(f"{n} ({c})" for n, c in top3) + ". "
            detail += f"Least loaded: {least[0]} ({least[1]} tasks). Ratio: {ratio:.1f}:1. "
            if profile.team_tier in ("solo", "small"):
                detail += "On a small team, some imbalance is expected — but this level of concentration creates risk if that person is unavailable."
            else:
                detail += "Teams that distribute work more evenly tend to close faster and have fewer single points of failure."
            findings.append(Finding(
                dimension="accountability",
                severity=severity,
                title=f"Workload imbalance — {most[0]} owns {pct:.0f}% of tasks",
                detail=detail,
                action=f"Redistribute tasks from {most[0]} to less-loaded team members. Consider whether some tasks can be delegated or cross-trained.",
                tier="fix_this_close"
            ))

    return findings


def analyze_controls(tasks: list, profile: CompanyProfile) -> list:
    findings = []
    is_audited = profile.audit_requirement != "none"

    # Overall reviewer coverage — break down by risk level
    # High-risk: JEs and recs always need review. Low-risk: custom/flux tasks.
    high_risk = [t for t in tasks if t.task_type in ("journal_entry", "rec_prepare_account")]
    low_risk = [t for t in tasks if t.task_type not in ("journal_entry", "rec_prepare_account")]
    hr_with_rev = sum(1 for t in high_risk if t.review_assignee)
    lr_with_rev = sum(1 for t in low_risk if t.review_assignee)
    has_reviewer = hr_with_rev + lr_with_rev
    total = len(tasks)
    pct = has_reviewer / total * 100 if total else 0
    hr_pct = hr_with_rev / len(high_risk) * 100 if high_risk else 100

    if pct < 80:
        # Focus the narrative on high-risk vs low-risk distinction
        if hr_pct < 80:
            severity = "critical" if is_audited and hr_pct < 50 else "warning"
            benchmark = f"Reviewer coverage is {pct:.0f}% overall ({has_reviewer} of {total} tasks). " \
                        f"More importantly, only {hr_pct:.0f}% of journal entries and reconciliations have reviewers ({hr_with_rev} of {len(high_risk)}). " \
                        f"These high-risk tasks are where review matters most for controls and audit readiness."
        else:
            severity = "info"
            benchmark = f"Reviewer coverage is {pct:.0f}% overall, but {hr_pct:.0f}% of your journal entries and reconciliations have reviewers — that's where it counts most. " \
                        f"The gap is mostly on custom tasks, which are lower risk."

        findings.append(Finding(
            dimension="controls",
            severity=severity,
            title=f"Reviewer coverage: {pct:.0f}% ({has_reviewer} of {total} tasks)",
            detail=benchmark,
            action="Prioritize adding reviewers to journal entries and reconciliations first — these carry the most audit and controls risk.",
            tier="fix_this_close" if hr_pct < 50 else "fix_this_quarter"
        ))

    # JE-specific reviewer gaps
    jes = [t for t in tasks if t.task_type == "journal_entry"]
    je_no_rev = [t for t in jes if not t.review_assignee]
    if je_no_rev and jes:
        je_pct = len(je_no_rev) / len(jes) * 100
        findings.append(Finding(
            dimension="controls",
            severity="critical",
            title=f"{len(je_no_rev)} of {len(jes)} journal entries have no reviewer ({je_pct:.0f}%)",
            detail=f"Journal entries are the #1 thing auditors look at. {len(je_no_rev)} of your {len(jes)} JEs don't have a reviewer — that's a significant controls gap. Audit-ready teams typically have 100% JE reviewer coverage.",
            action="Assign a reviewer to every journal entry. For segregation of duties, the reviewer should be someone different from the preparer.",
            tier="fix_now"
        ))

    # Rec-specific reviewer gaps
    recs = [t for t in tasks if t.task_type == "rec_prepare_account"]
    rec_no_rev = [t for t in recs if not t.review_assignee]
    if rec_no_rev and recs and is_audited:
        rec_pct = len(rec_no_rev) / len(recs) * 100
        if rec_pct > 30:
            findings.append(Finding(
                dimension="controls",
                severity="critical" if rec_pct > 70 else "warning",
                title=f"{len(rec_no_rev)} of {len(recs)} reconciliations have no reviewer ({rec_pct:.0f}%)",
                detail=f"{len(rec_no_rev)} of {len(recs)} reconciliations ({rec_pct:.0f}%) have no reviewer. For audited companies, unreviewed recs are a common audit finding. Teams that pass audits cleanly typically have reviewers on every rec.",
                action="Add reviewers to reconciliations, starting with your most material accounts. Even a quick sign-off adds a meaningful control layer.",
                tier="fix_this_close"
            ))

    return findings


def analyze_completeness(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    # Universal best practices gap
    checks = list(UNIVERSAL_ALWAYS)
    if profile.entity_count > 1:
        checks.extend(UNIVERSAL_MULTI_ENTITY)
    if profile.multi_currency:
        checks.extend(UNIVERSAL_MULTI_CURRENCY)
    if profile.audit_requirement != "none":
        checks.extend(UNIVERSAL_AUDITED)
    if profile.industry.lower() == "saas":
        checks.extend(UNIVERSAL_SAAS)
    if profile.industry.lower() == "manufacturing":
        checks.extend(UNIVERSAL_MANUFACTURING)

    missing = []
    for check in checks:
        if not check_task_matches(tasks, check["keywords"]):
            missing.append(check["name"])

    if missing:
        severity = "warning" if len(missing) >= 3 else "info"
        findings.append(Finding(
            dimension="completeness",
            severity=severity,
            title=f"{len(missing)} expected close tasks not found in your checklist",
            detail="Based on your company profile (" +
                   ", ".join(filter(None, [
                       f"{profile.entity_count} entities" if profile.entity_count > 1 else None,
                       f"multi-currency" if profile.multi_currency else None,
                       f"audited" if profile.audit_requirement != "none" else None,
                       profile.industry if profile.industry else None,
                   ])) +
                   "), typical checklists also include: " + ", ".join(missing) + ".",
            action="These may exist outside Numeric or under different names — but if they're part of your close, tracking them here gives you a single source of truth. Adding even 2-3 missing tasks usually improves visibility meaningfully.",
            tier="fix_this_quarter"
        ))

    # Category coverage
    uncategorized = [t for t in tasks if not t.properties.get("Category", "").strip()]
    if uncategorized:
        cat_pct = len(uncategorized) / len(tasks) * 100
        if cat_pct > 30:
            by_type = Counter(t.task_type for t in uncategorized)
            type_detail = ", ".join(f"{c} {t}" for t, c in by_type.most_common(3))
            findings.append(Finding(
                dimension="completeness",
                severity="warning",
                title=f"{cat_pct:.0f}% of tasks have no Category ({len(uncategorized)} of {len(tasks)})",
                detail=f"Uncategorized tasks break down as: {type_detail}. Categories let you track progress by accounting area (Cash, AR, Payroll, etc.) — most teams that use them say it's one of the first things they look at during the close.",
                action="Bulk-assign Category tags. Start with flux and reconciliation tasks — they benefit most from area-level grouping.",
                tier="fix_this_close"
            ))

    # Non-close separation
    non_close_keywords = ["non-close", "non close", "tax filing", "compliance", "board report", "annual report"]
    non_close_tasks = []
    for t in tasks:
        name_lower = t.name.lower()
        for kw in non_close_keywords:
            if kw in name_lower:
                non_close_tasks.append(t)
                break

    # Check if they have exclude-from-progress set up
    exclude_tags = []
    for tg in profile.tag_groups:
        for opt in tg.get("options", []):
            if opt.get("exclude_from_progress"):
                exclude_tags.append(f"{tg['name']}: {opt['name']}")

    if exclude_tags and not profile.has_non_close_exclusion:
        # They have some exclusions but maybe not for non-close specifically
        pass

    return findings


def analyze_structure(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    # Due date distribution
    due_counts = Counter()
    person_day = defaultdict(lambda: defaultdict(int))
    for t in tasks:
        if t.prep_due:
            due_counts[t.prep_due] += 1
            if t.prep_assignee:
                person_day[t.prep_assignee][t.prep_due] += 1

    if due_counts:
        total_with_dues = sum(due_counts.values())
        most_day, most_count = due_counts.most_common(1)[0]
        most_pct = most_count / total_with_dues * 100

        # Scale threshold with close window: for a 3-day close, 33% per day is the minimum
        # For a 5-day close, 25% is reasonable. Only flag if concentration is avoidable.
        unique_days = len(due_counts)
        fair_share_pct = 100.0 / max(unique_days, 1)
        # Flag if the busiest day has more than 2x what an even distribution would give
        bottleneck_threshold_pct = max(30, fair_share_pct * 2)

        if most_pct > bottleneck_threshold_pct and most_count >= 10:
            findings.append(Finding(
                dimension="structure",
                severity="warning",
                title=f"Bottleneck day: {most_count} tasks due on {most_day} ({most_pct:.0f}% of total)",
                detail=f"Having {most_pct:.0f}% of tasks due on a single day creates a bottleneck that increases error risk and makes it hard to catch up if anything slips. The next busiest days: " +
                       ", ".join(f"{d} ({c})" for d, c in due_counts.most_common(4)[1:]) + ". Teams with smoother close timelines tend to spread tasks more evenly across the window.",
                action=f"Move lower-priority or non-dependent tasks off {most_day}. Even shifting 5-10 tasks earlier can meaningfully reduce the crunch.",
                tier="fix_this_close"
            ))

    # Per-person bottleneck
    bottleneck_threshold = 15 if profile.team_tier == "large" else 10 if profile.team_tier == "mid" else 8
    person_bottlenecks = []
    for person, days in person_day.items():
        for day, count in days.items():
            if count > bottleneck_threshold:
                person_bottlenecks.append((person, day, count))

    if person_bottlenecks:
        person_bottlenecks.sort(key=lambda x: -x[2])
        top = person_bottlenecks[:3]
        detail = "; ".join(f"{p} has {c} tasks on {d}" for p, d, c in top)
        findings.append(Finding(
            dimension="structure",
            severity="warning",
            title=f"{len(person_bottlenecks)} person-day bottleneck{'s' if len(person_bottlenecks) > 1 else ''}",
            detail=f"Individual team members have too many tasks concentrated on a single day: {detail}. When someone has {bottleneck_threshold}+ tasks due on one day, quality drops and things get missed.",
            action=f"Stagger due dates so no one has more than {bottleneck_threshold} tasks on any given day. Look for tasks that don't depend on each other and can be moved a day earlier or later.",
            tier="fix_this_close"
        ))

    # Pre-close tasks
    if profile.period_end:
        try:
            month_end = datetime.strptime(profile.period_end, "%Y-%m-%d")
            pre_close = [t for t in tasks if t.prep_due and datetime.strptime(t.prep_due, "%Y-%m-%d") <= month_end]
            if not pre_close:
                findings.append(Finding(
                    dimension="structure",
                    severity="info",
                    title="No pre-close tasks detected",
                    detail="The fastest-closing teams almost always have a few tasks before month-end: cutoff notifications, system sync, department reminders. Pre-close prep is what separates a reactive close from a proactive one.",
                    action="Add 2-3 pre-close tasks (e.g., 'Send close calendar to departments', 'Confirm all sub-ledger entries posted', 'Set AP/AR cutoff'). These typically take 5 minutes to create and save hours during the close.",
                    tier="fix_this_quarter"
                ))
        except ValueError:
            pass

    # Due date gaps (back-loading)
    if len(due_counts) >= 3:
        sorted_dates = sorted(due_counts.keys())
        try:
            date_objs = [datetime.strptime(d, "%Y-%m-%d") for d in sorted_dates]
            # Check for gaps > 2 business days
            gaps = []
            for i in range(len(date_objs) - 1):
                diff = (date_objs[i+1] - date_objs[i]).days
                if diff > 4:  # More than a long weekend gap
                    gaps.append((sorted_dates[i], sorted_dates[i+1], diff))
            if gaps:
                gap_detail = "; ".join(f"{g[0]} to {g[1]} ({g[2]} days)" for g in gaps[:3])
                findings.append(Finding(
                    dimension="structure",
                    severity="info",
                    title=f"{len(gaps)} gap{'s' if len(gaps) > 1 else ''} in your close timeline",
                    detail=f"There are periods with no tasks due: {gap_detail}. This may indicate back-loading.",
                    action="Review whether tasks could be moved earlier to spread work more evenly.",
                    tier="fix_this_quarter"
                ))
        except ValueError:
            pass

    return findings


def analyze_properties(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    for tg in profile.tag_groups:
        tg_name = tg.get("name", "")
        is_required = tg.get("is_required", False)
        option_count = len(tg.get("options", []))

        if not tg_name or tg_name == "Category":  # Category handled in completeness
            continue

        # Count population — use relevant tasks as denominator
        # Rec and flux tasks often inherit properties from their report config,
        # so empty at the task level doesn't mean untagged. Focus on custom + JE tasks.
        relevant_tasks = [t for t in tasks if t.task_type in ("custom", "journal_entry")]
        if not relevant_tasks:
            relevant_tasks = tasks  # Fallback to all tasks if no custom/JE
        populated = sum(1 for t in tasks if t.properties.get(tg_name, "").strip())
        populated_relevant = sum(1 for t in relevant_tasks if t.properties.get(tg_name, "").strip())
        pct = populated_relevant / len(relevant_tasks) * 100 if relevant_tasks else 0

        if option_count == 0:
            findings.append(Finding(
                dimension="properties",
                severity="info",
                title=f'"{tg_name}" property has no options configured',
                detail=f"This tag group exists but has zero options defined. It's an empty shell adding clutter to your workspace.",
                action=f"Either set up options for \"{tg_name}\" or remove it entirely.",
                tier="fix_this_quarter"
            ))
        elif pct == 0:
            findings.append(Finding(
                dimension="properties",
                severity="info",
                title=f'"{tg_name}" property is defined but never used (0%)',
                detail=f"This tag group has {option_count} options configured but no tasks are tagged. Empty properties add visual clutter and decision fatigue for your team.",
                action=f"Either commit to populating \"{tg_name}\" (even partially) or remove it. 3-5 well-used properties are typically more useful than 8+ that are half-empty.",
                tier="fix_this_quarter"
            ))
        elif 0 < pct < 20 and option_count >= 3:
            findings.append(Finding(
                dimension="properties",
                severity="warning",
                title=f'"{tg_name}" property is barely adopted ({pct:.0f}%, {populated} of {len(tasks)} tasks)',
                detail=f"This property has {option_count} options but only {pct:.0f}% of tasks use it. It was set up but never stuck — this is common when a property is created during setup but doesn't become part of the team's workflow.",
                action=f"Decide: commit to populating \"{tg_name}\" (you can bulk-tag existing tasks) or remove it. Partial adoption often creates more confusion than having no property at all.",
                tier="fix_this_close"
            ))
        elif is_required and pct < 50:
            findings.append(Finding(
                dimension="properties",
                severity="warning",
                title=f'Required property "{tg_name}" only {pct:.0f}% populated',
                detail=f"This property is marked as required but only {populated} of {len(tasks)} tasks have it set.",
                action=f"Bulk-assign \"{tg_name}\" values to the {len(tasks) - populated} untagged tasks.",
                tier="fix_this_close"
            ))

    # Category-entity overlap
    entity_names_lower = {e.lower() for e in profile.entities}
    cat_tg = next((tg for tg in profile.tag_groups if tg.get("name") == "Category"), None)
    if cat_tg:
        overlaps = []
        for opt in cat_tg.get("options", []):
            opt_name = opt.get("name", "")
            if opt_name.lower() in entity_names_lower or any(en in opt_name.lower() for en in entity_names_lower if len(en) > 3):
                overlaps.append(opt_name)
        if overlaps:
            findings.append(Finding(
                dimension="properties",
                severity="info",
                title=f"Category values overlap with entity names: {', '.join(overlaps)}",
                detail="Using Category for entity-specific tasks makes it harder to filter by both account area and entity independently.",
                action="Consider using the Entity property tag instead, and reserve Category for accounting areas (Cash, AR, AP, etc.).",
                tier="fix_this_quarter"
            ))

    # Unused progress exclusions
    for tg in profile.tag_groups:
        for opt in tg.get("options", []):
            if opt.get("exclude_from_progress"):
                # Check if any tasks use this option
                opt_name = opt.get("name", "")
                used = sum(1 for t in tasks if opt_name in t.properties.get(tg["name"], ""))
                if used == 0:
                    findings.append(Finding(
                        dimension="properties",
                        severity="info",
                        title=f'"{tg["name"]}: {opt_name}" excludes from progress but is unused',
                        detail=f"This tag option is configured to exclude tasks from close progress tracking, but no tasks use it.",
                        action=f"If you have non-close tasks (audit prep, tax filings), tag them with \"{opt_name}\" to clean up your progress metrics.",
                        tier="fix_this_quarter"
                    ))

    return findings


def analyze_timeline(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    if profile.close_window_days > 0:
        cwd = profile.close_window_days

        # Adjust benchmarks for complexity: multi-entity, multi-currency, and industry
        # Simple: single entity, no special industry → standard benchmarks
        # Complex: 5+ entities, multi-currency, manufacturing/FS → extended benchmarks
        complexity_adj = 0
        if profile.entity_count >= 5:
            complexity_adj += 2
        elif profile.entity_count >= 3:
            complexity_adj += 1
        if profile.multi_currency:
            complexity_adj += 1
        if profile.industry.lower() in ("manufacturing", "financial services", "healthcare"):
            complexity_adj += 2

        # Base benchmarks: exceptional=3, strong=5, avg=7, below=10
        # Each complexity point shifts thresholds up by ~1 day
        exc_threshold = 3 + complexity_adj
        strong_threshold = 5 + complexity_adj
        avg_threshold = 7 + complexity_adj
        below_threshold = 10 + complexity_adj

        if cwd <= exc_threshold:
            tier_label = "Exceptional"
        elif cwd <= strong_threshold:
            tier_label = "Strong"
        elif cwd <= avg_threshold:
            tier_label = "Average"
        elif cwd <= below_threshold:
            tier_label = "Below average"
        else:
            tier_label = "Needs improvement"

        detail = f"Your close spans {cwd} business days ({profile.close_start} to {profile.close_end}). "
        if complexity_adj > 0:
            complexity_note = []
            if profile.entity_count >= 3:
                complexity_note.append(f"{profile.entity_count} entities")
            if profile.multi_currency:
                complexity_note.append("multi-currency")
            if profile.industry.lower() in ("manufacturing", "financial services", "healthcare"):
                complexity_note.append(f"{profile.industry} complexity")
            detail += f"Given your complexity ({', '.join(complexity_note)}), benchmarks are adjusted accordingly. "

        if cwd <= strong_threshold:
            detail += "That's strong for your profile — you're performing well relative to similar organizations."
        elif cwd <= avg_threshold:
            detail += f"That's about average for organizations with your complexity. Top performers in your category typically close in {exc_threshold}-{strong_threshold} business days."
        elif cwd <= below_threshold:
            detail += f"There's likely room to tighten this up with better task sequencing and pre-close prep. Teams with similar complexity typically close in {strong_threshold}-{avg_threshold} business days."
        else:
            detail += f"A close this long usually signals opportunities in automation, dependency management, or pre-close preparation. Teams with similar complexity typically close in {avg_threshold}-{below_threshold} business days."

        findings.append(Finding(
            dimension="timeline",
            severity="info",
            title=f"Close window: {cwd} business days — {tier_label}",
            detail=detail,
            action="" if cwd <= avg_threshold else "Focus on automating reconciliations and reducing cross-department dependencies to shorten your close.",
            tier="fix_this_quarter"
        ))

    if profile.target_close_days > 0 and profile.close_window_days > 0:
        gap = profile.close_window_days - profile.target_close_days
        if gap > 3:
            findings.append(Finding(
                dimension="timeline",
                severity="warning",
                title=f"Close window ({profile.close_window_days} days) exceeds your target ({profile.target_close_days} days) by {gap} days",
                detail=f"You're {gap} days off your target — that's a meaningful gap. Usually the difference isn't speed of execution but structure: pre-close prep, better sequencing, and fewer bottleneck days.",
                action="Identify the 3-5 tasks with the latest due dates and evaluate: can they be started earlier, automated, or run in parallel with something else?",
                tier="fix_this_quarter"
            ))

    # Holiday calendar check — context-aware for global/multi-entity companies
    if not profile.from_csv and not profile.holidays:
        # Multi-entity companies with multiple currencies (global operations) may
        # intentionally skip a single holiday calendar since teams in different
        # countries observe different holidays
        if profile.entity_count >= 5 and profile.multi_currency:
            findings.append(Finding(
                dimension="timeline",
                severity="info",
                title="No holiday calendar configured",
                detail=f"Your workspace has {profile.entity_count} entities across multiple currencies, suggesting global operations. "
                       "A single holiday calendar may not work for your team — but without one, Numeric calculates due dates using calendar days, "
                       "which may cause tasks to land on local holidays.",
                action="Consider adding at least your headquarters' or primary close team's holidays. Numeric applies holidays workspace-wide, "
                       "so focus on the days when your core close team is off.",
                tier="fix_this_quarter"
            ))
        else:
            findings.append(Finding(
                dimension="timeline",
                severity="warning",
                title="No holiday calendar configured",
                detail="Your workspace has no holidays set up. Without a holiday calendar, Numeric calculates due dates using calendar days "
                       "instead of business days — which means tasks may appear due on holidays or weekends, and your close timeline metrics will be inaccurate.",
                action="Go to Settings → Holidays and add your company's observed holidays. This ensures due dates land on real working days "
                       "and your close window is measured in actual business days.",
                tier="fix_now"
            ))
    elif not profile.from_csv and profile.holidays:
        # Check if holidays are stale (none in current or future year)
        current_year = datetime.now().year
        future_holidays = [h for h in profile.holidays
                          if h.get("recurs_yearly") or h.get("start", {}).get("year", 0) >= current_year]
        if not future_holidays:
            findings.append(Finding(
                dimension="timeline",
                severity="info",
                title="Holiday calendar may be outdated",
                detail=f"Your holiday calendar has no entries for {current_year} or later (and no recurring holidays). Due dates may land on holidays if the calendar isn't kept current.",
                action=f"Review Settings → Holidays and add your {current_year} holidays, or set existing holidays to recur yearly.",
                tier="fix_this_close"
            ))

    # Self-reported vs detected close window
    if profile.current_close_days > 0 and profile.close_window_days > 0:
        detected = profile.close_window_days
        reported = profile.current_close_days
        if detected > reported + 2:
            findings.append(Finding(
                dimension="timeline",
                severity="warning",
                title=f"Your checklist spans {detected} business days — but you said your close takes {reported}",
                detail=f"You told us your close takes {reported} business days, but your earliest task is due {profile.close_start} and your latest is {profile.close_end} — that's {detected} business days of task coverage. "
                       f"This usually means some tasks are running outside the 'official' close window (pre-close prep, board reporting, StratFin) and should be tagged as non-close, or your close is actually longer than you think.",
                action=f"Review tasks before your close start and after Day {reported}. Create a 'Non-Close' tag group with exclude_from_progress enabled, then tag tasks like board reporting, tax filings, and admin work so they don't distort your close progress metrics.",
                tier="fix_this_close"
            ))

    return findings


def analyze_hygiene(tasks: list, profile: CompanyProfile) -> list:
    findings = []

    # Description coverage
    no_desc = [t for t in tasks if not t.description]
    if no_desc:
        pct = len(no_desc) / len(tasks) * 100
        je_no_desc = [t for t in no_desc if t.task_type == "journal_entry"]
        if pct > 50:
            severity = "info"
            if je_no_desc:
                severity = "warning"
                detail = f"{pct:.0f}% of tasks have no description ({len(no_desc)} of {len(tasks)}). {len(je_no_desc)} are journal entries — these especially need descriptions for audit trail. Think of descriptions as your team's backup plan: if someone is out sick, can their colleague pick up the task?"
            else:
                detail = f"{pct:.0f}% of tasks have no description. Descriptions are one of the highest-leverage improvements you can make — they help with onboarding, backup coverage, and audit documentation. Teams that add descriptions typically see fewer questions during the close."
            findings.append(Finding(
                dimension="hygiene",
                severity=severity,
                title=f"{pct:.0f}% of tasks have no description",
                detail=detail,
                action="Start with journal entries and complex reconciliations. A good description answers: what system to use, what the expected output is, and what to do if something looks off.",
                tier="fix_this_quarter"
            ))

    # Multi-report analysis
    reports = Counter(t.report_id for t in tasks)
    if len(reports) > 1:
        report_parts = []
        for i, (r, c) in enumerate(reports.most_common(), 1):
            # Try to infer a friendlier name from the report ID
            if "checklist" in r.lower():
                label = "Checklist"
            elif r.startswith("fcg_"):
                label = f"Reconciliation report"
            else:
                label = f"Report {i}"
            report_parts.append(f"{label} ({c} tasks)")
        detail = f"Tasks are spread across {len(reports)} reports: " + ", ".join(report_parts)
        detail += ". Multiple reports are fine if they serve different purposes (e.g., close checklist vs. reconciliations). Check that tasks aren't duplicated across reports."
        findings.append(Finding(
            dimension="hygiene",
            severity="info",
            title=f"Tasks distributed across {len(reports)} reports",
            detail=detail,
            action="Ensure each report has a clear purpose. Consider consolidating if reports overlap in scope.",
            tier="fix_this_quarter"
        ))

    return findings


def analyze_late_submissions(tasks: list, profile: CompanyProfile) -> list:
    """Flag tasks submitted after their due date."""
    findings = []
    late_tasks = []
    for t in tasks:
        if t.prep_due and hasattr(t, '_prep_submitted_at') and t._prep_submitted_at:
            try:
                due = datetime.strptime(t.prep_due, "%Y-%m-%d")
                submitted = datetime.strptime(t._prep_submitted_at[:10], "%Y-%m-%d")
                if submitted > due:
                    days_late = (submitted - due).days
                    late_tasks.append((t, days_late))
            except ValueError:
                pass

    if late_tasks:
        late_tasks.sort(key=lambda x: -x[1])
        total_with_due = sum(1 for t in tasks if t.prep_due and t.prep_status == "COMPLETE")
        pct = len(late_tasks) / total_with_due * 100 if total_with_due else 0
        top = late_tasks[:5]
        detail = f"{len(late_tasks)} of {total_with_due} completed tasks ({pct:.0f}%) were submitted after their due date. "
        detail += "Top offenders: " + "; ".join(f'"{t.name[:50]}" ({d}d late)' for t, d in top)
        if len(late_tasks) > 5:
            detail += f" ...and {len(late_tasks) - 5} more"
        detail += ". Late submissions often signal unrealistic due dates, unclear ownership, or tasks stuck waiting on upstream dependencies."

        severity = "warning" if pct > 30 else "info"
        findings.append(Finding(
            dimension="accountability",
            severity=severity,
            title=f"{len(late_tasks)} tasks submitted late ({pct:.0f}%)",
            detail=detail,
            action="Review the most-late tasks: are due dates realistic? Are there upstream blockers? Consider adjusting due dates or adding dependency reminders.",
            tier="fix_this_close" if pct > 50 else "fix_this_quarter",
            affected_tasks=[t.name for t, _ in late_tasks],
        ))

    return findings


def analyze_pre_close_opportunities(tasks: list, profile: CompanyProfile) -> list:
    """Identify tasks that could be moved to pre-close (before month-end) to shorten the close."""
    findings = []
    if not profile.period_end:
        return findings

    # Pre-close candidates: tasks that don't depend on month-end actuals
    pre_close_keywords = ["cutoff", "notify", "remind", "send email", "kick off", "kickoff",
                          "obtain", "request", "prepare template", "set up", "configure",
                          "clean up", "reconcile bank", "archive", "backup", "training",
                          "update access", "review policy", "schedule"]
    non_pre_close_keywords = ["accru", "journal entry", "je ", "post ", "book ", "flux",
                              "reconcil", "consolidat", "eliminat", "report", "review note",
                              "close period", "lock period"]

    candidates = []
    try:
        period_end = datetime.strptime(profile.period_end, "%Y-%m-%d")
    except ValueError:
        return findings

    for t in tasks:
        if not t.prep_due:
            continue
        try:
            due = datetime.strptime(t.prep_due, "%Y-%m-%d")
        except ValueError:
            continue

        # Only look at tasks in the first 2 days of close
        if due > period_end + timedelta(days=3):
            continue

        name_lower = t.name.lower()
        # Skip tasks that clearly need month-end actuals
        if any(kw in name_lower for kw in non_pre_close_keywords):
            continue
        # Check for pre-close signals
        if any(kw in name_lower for kw in pre_close_keywords):
            days_offset = (due - period_end).days
            candidates.append((t, days_offset))

    if candidates and len(candidates) >= 2:
        detail = f"{len(candidates)} tasks in the first days of close could potentially be moved to pre-close (before month-end), freeing up capacity during the crunch. "
        detail += "Examples: " + ", ".join(f'"{t.name[:50]}"' for t, _ in candidates[:5])
        if len(candidates) > 5:
            detail += f" ...and {len(candidates) - 5} more"
        findings.append(Finding(
            dimension="structure",
            severity="info",
            title=f"{len(candidates)} tasks could move to pre-close",
            detail=detail,
            action="Move these tasks to negative due dates (e.g., Day -2, Day -1) so they happen before month-end. This is one of the fastest ways to shorten your close window.",
            tier="fix_this_quarter",
            affected_tasks=[t.name for t, _ in candidates],
        ))

    return findings


# ============================================================
# New Analyzers: Miscategorization, Dependencies, JE Deep Dive
# ============================================================

# Category keyword map — maps keywords in task names to expected Category values
CATEGORY_KEYWORDS = {
    "cash": ["bank", "cash", "petty cash", "wire", "ach", "lockbox"],
    "accounts receivable": ["accounts receivable", "ar aging", "ar reconcil", "revenue rec", "billing", "customer refund", "bad debt", "allowance for doubtful"],
    "prepaids": ["prepaid", "prepayment", "amortiz", "insurance premium", "advance payment"],
    "fixed asset": ["fixed asset", "depreciat", "capitali", "fa reconcil", "asset disposal", "asset retire", "property plant"],
    "accounts payable": ["accounts payable", "ap aging", "ap reconcil", "vendor", "ap accrual"],
    "accruals": ["accrual", "accrued", "accrue", "provision"],
    "revenue": ["revenue", "deferred rev", "asc 606", "contract liab", "unearned", "subscription rev", "mrr"],
    "equity": ["equity", "stock comp", "share-based", "stock option", "rsu", "treasury stock", "retained earning"],
    "payroll": ["payroll", "salary", "wage", "bonus", "commission accru", "benefits", "401k", "pto"],
    "tax": ["tax", "income tax", "sales tax", "vat", "gst", "withholding", "tax provision"],
    "intercompany": ["intercompany", "ic elim", "interco", "transfer pricing"],
    "reporting": ["financial report", "close package", "board report", "management report", "consolidat", "reporting"],
    "leases": ["lease", "rou ", "right of use", "asc 842", "operating lease", "finance lease"],
}


def normalize_category(cat_value: str) -> str:
    """Normalize a category value to match our keyword map keys."""
    if not cat_value:
        return ""
    cl = cat_value.lower()
    for key in CATEGORY_KEYWORDS:
        if key in cl:
            return key
    return cl


def analyze_miscategorization(tasks: list, profile: CompanyProfile) -> list:
    """Detect tasks that appear to be in the wrong category based on name keywords."""
    findings = []
    miscat = []

    # Cross-category terms that are legitimately used in multiple contexts
    # Don't flag these as miscategorized when they appear in related categories
    CROSS_CATEGORY_EXCEPTIONS = {
        "vendor": {"accruals", "accruals and other current liabilities"},
        "bonus": {"capitalized commission", "compensation", "equity"},
        "commission": {"capitalized commission", "compensation", "equity"},
        "accrued": {"capitalized commission", "compensation", "payroll", "revenue", "tax", "cogs"},
        "accrue": {"capitalized commission", "compensation", "payroll", "revenue", "tax", "cogs"},
        "accrual": {"capitalized commission", "compensation", "payroll", "revenue", "tax", "cogs"},
        "lease": {"accruals", "accruals and other current liabilities", "prepaids"},
        "insurance": {"accruals", "prepaids", "prepaids and other current assets"},
        "depreciat": {"non current assets", "fixed assets"},
        "amortiz": {"non current assets", "capitalized commission", "prepaids"},
        "reclass": set(),  # reclass tasks legitimately appear in any category
        "reconcile": set(),  # recs appear everywhere
        "review": set(),  # reviews appear everywhere
        "post": set(),  # posting tasks appear everywhere
        "book": set(),  # booking tasks appear everywhere
        "record": set(),  # recording tasks appear everywhere
    }

    for t in tasks:
        cat = t.properties.get("Category", "").strip()
        if not cat:
            continue

        name_lower = t.name.lower()
        desc_lower = (t.description or "").lower()
        combined = name_lower + " " + desc_lower
        cat_normalized = normalize_category(cat)
        cat_lower = cat.lower()

        # Check if the task name suggests a different category
        for expected_cat, keywords in CATEGORY_KEYWORDS.items():
            if expected_cat == cat_normalized:
                continue
            for kw in keywords:
                if kw in combined and len(kw) > 3:  # Skip very short keywords
                    # Strong signal: task name matches a different category's keywords
                    # Avoid false positives: don't flag if the keyword is part of the assigned category
                    if kw not in cat.lower():
                        # Check cross-category exceptions
                        is_exception = False
                        for exc_kw, exc_cats in CROSS_CATEGORY_EXCEPTIONS.items():
                            if kw.startswith(exc_kw) or exc_kw in kw:
                                if not exc_cats or cat_lower in exc_cats or any(ec in cat_lower for ec in exc_cats):
                                    is_exception = True
                                    break
                        if is_exception:
                            continue
                        miscat.append({
                            "task": t.name,
                            "current_cat": cat,
                            "suggested_cat": expected_cat.title(),
                            "keyword": kw,
                        })
                    break

    # Deduplicate — one task might match multiple categories, keep the first
    seen = set()
    unique_miscat = []
    for m in miscat:
        if m["task"] not in seen:
            seen.add(m["task"])
            unique_miscat.append(m)

    if unique_miscat:
        # Group by current → suggested for cleaner output
        top = unique_miscat[:10]
        detail_lines = []
        for m in top:
            detail_lines.append(f'"{m["task"][:60]}" is categorized as {m["current_cat"]} but mentions "{m["keyword"]}" (→ {m["suggested_cat"]})')

        findings.append(Finding(
            dimension="completeness",
            severity="warning" if len(unique_miscat) >= 5 else "info",
            title=f"{len(unique_miscat)} tasks may be miscategorized",
            detail="These tasks have names/descriptions that suggest they belong in a different category:\n" + "\n".join(f"• {d}" for d in detail_lines) +
                   (f"\n...and {len(unique_miscat) - 10} more" if len(unique_miscat) > 10 else ""),
            action="Review these tasks and update their Category tags. Accurate categorization makes your close progress by area much more meaningful — most teams that invest 15 minutes in cleanup say it's worth it.",
            tier="fix_this_close",
            affected_tasks=[m["task"] for m in unique_miscat],
        ))

    return findings


def analyze_dependencies(tasks: list, profile: CompanyProfile) -> list:
    """Detect logical dependency issues — tasks that should come before others but are due later."""
    findings = []

    # Build lookup of tasks by type and category
    tasks_by_type = defaultdict(list)
    for t in tasks:
        if t.prep_due:
            tasks_by_type[t.task_type].append(t)

    # Known dependency patterns:
    # 1. Reconciliations should be done before flux analysis on the same account
    # 2. JEs should be posted before their corresponding rec/flux review
    # 3. Intercompany elimination should come after entity-level tasks
    # 4. Reporting/close package should be the last tasks
    # 5. Bank rec should precede cash-related accruals
    dependency_violations = []

    # Pattern: Flux tasks due before their corresponding rec tasks
    recs = [t for t in tasks if t.task_type == "rec_prepare_account" and t.prep_due]
    fluxes = [t for t in tasks if t.task_type == "flux" and t.prep_due]

    # Match recs and fluxes by account (from key_id or name overlap)
    rec_lookup = {}
    for r in recs:
        # Extract account identifier from name (e.g., "Reconcile Cash (1000)" → "1000")
        name_parts = r.name.lower()
        rec_lookup[name_parts] = r

    for fx in fluxes:
        fx_name = fx.name.lower()
        # Check if there's a rec for a similar account
        for rec_name, rec_task in rec_lookup.items():
            # Simple overlap check — if both reference the same account number or name
            # Extract account codes from names
            fx_acct = fx.key_id.split("/")[-1] if "/" in fx.key_id else ""
            rec_acct = rec_task.key_id.split("/")[-1] if "/" in rec_task.key_id else ""
            if fx_acct and rec_acct and fx_acct == rec_acct:
                try:
                    fx_date = datetime.strptime(fx.prep_due, "%Y-%m-%d")
                    rec_date = datetime.strptime(rec_task.prep_due, "%Y-%m-%d")
                    if fx_date < rec_date:
                        dependency_violations.append({
                            "blocker": rec_task.name[:60],
                            "blocked": fx.name[:60],
                            "blocker_due": rec_task.prep_due,
                            "blocked_due": fx.prep_due,
                            "issue": "Flux review is due before its reconciliation"
                        })
                except ValueError:
                    pass

    # Pattern: Reporting tasks due before close tasks complete
    cat_prop = "Category"
    reporting_tasks = [t for t in tasks if "reporting" in (t.properties.get(cat_prop, "") or "").lower()
                       or "close package" in t.name.lower()
                       or "financial statement" in t.name.lower()
                       or "management review" in t.name.lower()]
    close_tasks = [t for t in tasks if t.prep_due and t not in reporting_tasks
                   and t.properties.get(cat_prop, "").strip()
                   and "reporting" not in (t.properties.get(cat_prop, "") or "").lower()]

    if reporting_tasks and close_tasks:
        close_dates = sorted([t.prep_due for t in close_tasks if t.prep_due])
        if close_dates:
            # Use 90th percentile of close dates — not the absolute latest
            # This avoids false positives from one late-due outlier task
            p90_idx = int(len(close_dates) * 0.9)
            p90_close = close_dates[min(p90_idx, len(close_dates) - 1)]
            # Only flag reporting tasks due significantly before the bulk of close tasks
            early_reports = [t for t in reporting_tasks if t.prep_due and t.prep_due < p90_close]
            if early_reports:
                for r in early_reports[:3]:
                    dependency_violations.append({
                        "blocker": "Bulk of close tasks (90th pct: " + p90_close + ")",
                        "blocked": r.name[:60],
                        "blocker_due": p90_close,
                        "blocked_due": r.prep_due,
                        "issue": "Reporting task is due before most close tasks complete — verify this is an intentional interim review"
                    })

    # Pattern: Intercompany tasks due before entity-level tasks
    # Note: different entities may close on different days (staggered close),
    # so we use the median entity task date rather than the absolute latest
    ic_tasks = [t for t in tasks if "intercompany" in t.name.lower() or "ic elim" in t.name.lower()
                or "consolidat" in t.name.lower()]
    entity_tasks = [t for t in tasks if t.prep_due and t not in ic_tasks
                    and t.properties.get("Entity", "").strip()]

    if ic_tasks and entity_tasks:
        entity_dates = sorted([t.prep_due for t in entity_tasks if t.prep_due])
        if entity_dates:
            # Use 80th percentile — IC should happen after most (not necessarily all) entity work
            p80_idx = int(len(entity_dates) * 0.8)
            p80_entity = entity_dates[min(p80_idx, len(entity_dates) - 1)]
            early_ic = [t for t in ic_tasks if t.prep_due and t.prep_due < p80_entity]
            if early_ic:
                for ic in early_ic[:3]:
                    dependency_violations.append({
                        "blocker": "Entity-level tasks (80th pct: " + p80_entity + ")",
                        "blocked": ic.name[:60],
                        "blocker_due": p80_entity,
                        "blocked_due": ic.prep_due,
                        "issue": "IC/consolidation task due before entity tasks finish"
                    })

    if dependency_violations:
        top = dependency_violations[:5]
        detail_lines = [f'"{v["blocked"]}" (due {v["blocked_due"]}) depends on "{v["blocker"]}" (due {v["blocker_due"]}) — {v["issue"]}' for v in top]
        findings.append(Finding(
            dimension="structure",
            severity="warning" if len(dependency_violations) >= 3 else "info",
            title=f"{len(dependency_violations)} potential dependency/sequencing issue{'s' if len(dependency_violations) != 1 else ''}",
            detail="These tasks appear to be scheduled in the wrong order:\n" + "\n".join(f"• {d}" for d in detail_lines) +
                   (f"\n...and {len(dependency_violations) - 5} more" if len(dependency_violations) > 5 else ""),
            action="Review due date sequencing. The general pattern: JEs → recs → flux reviews → reporting. Teams with clean dependency chains tend to have fewer surprises late in the close.",
            tier="fix_this_close",
            affected_tasks=[v["blocked"] for v in dependency_violations],
        ))

    return findings


def analyze_flux_tasks(tasks: list, profile: CompanyProfile) -> list:
    """Analyze flux tasks separately — these are threshold-based monitoring tasks, not action tasks.

    Flux tasks only need to be completed when variance exceeds a threshold. This makes them
    fundamentally different from JEs, recs, and custom tasks:
    - Completion rate is NOT a quality signal (low completion may mean low variance, which is good)
    - But they still need reviewers, categories, and proper due dates
    - They should pair with reconciliation tasks for the same accounts
    - They represent the analytical layer of the close, not the operational layer
    """
    findings = []
    fluxes = [t for t in tasks if t.task_type == "flux"]
    non_flux = [t for t in tasks if t.task_type != "flux"]

    if not fluxes:
        return findings

    flux_pct = len(fluxes) / len(tasks) * 100

    # --- Flux tasks without reviewers ---
    flux_no_rev = [t for t in fluxes if not t.review_assignee]
    if flux_no_rev:
        no_rev_pct = len(flux_no_rev) / len(fluxes) * 100
        if no_rev_pct > 50:
            findings.append(Finding(
                dimension="controls",
                severity="warning",
                title=f"{len(flux_no_rev)} of {len(fluxes)} flux tasks have no reviewer ({no_rev_pct:.0f}%)",
                detail="Flux reviews are how your team spots anomalies. Without a reviewer, there's no second pair of eyes "
                       "on variance explanations. Teams with strong analytical controls typically assign reviewers to their flux tasks — it's a lightweight way to add a check on the numbers.",
                action="Assign reviewers to flux tasks, prioritizing high-risk accounts (cash, revenue, material expense lines). This is usually a quick win.",
                tier="fix_this_close",
                affected_tasks=[t.name for t in flux_no_rev[:20]],
            ))

    # --- Flux tasks without categories ---
    flux_no_cat = [t for t in fluxes if not t.properties.get("Category", "").strip()]
    if flux_no_cat:
        no_cat_pct = len(flux_no_cat) / len(fluxes) * 100
        if no_cat_pct > 50:
            findings.append(Finding(
                dimension="completeness",
                severity="info",
                title=f"{len(flux_no_cat)} of {len(fluxes)} flux tasks have no Category ({no_cat_pct:.0f}%)",
                detail="Uncategorized flux tasks make it harder to track variance analysis by accounting area. "
                       "Categories let you see at a glance which areas have been reviewed.",
                action="Bulk-assign Category tags to flux tasks. They should match the categories used for corresponding reconciliations.",
                tier="fix_this_quarter",
                affected_tasks=[t.name for t in flux_no_cat[:15]],
            ))

    # --- Flux tasks without preparers ---
    flux_no_prep = [t for t in fluxes if not t.prep_assignee]
    if flux_no_prep and len(flux_no_prep) > 5:
        findings.append(Finding(
            dimension="accountability",
            severity="warning",
            title=f"{len(flux_no_prep)} flux tasks have no preparer assigned",
            detail="Even though flux tasks are threshold-based, someone needs to own the variance review. "
                   "Unassigned flux tasks risk being overlooked when variances are material. Flux ownership is typically assigned to the same person who owns the rec for that account.",
            action="Assign preparers to flux tasks — typically the same person who owns the reconciliation for each account.",
            tier="fix_this_close",
            affected_tasks=[t.name for t in flux_no_prep[:15]],
        ))

    # --- Flux without corresponding recs (orphan fluxes) ---
    recs = [t for t in tasks if t.task_type == "rec_prepare_account"]
    if recs and fluxes:
        # Match by key_id (account)
        rec_accounts = set()
        for r in recs:
            if r.key_id:
                acct = r.key_id.split("/")[-1] if "/" in r.key_id else r.key_id
                rec_accounts.add(acct)

        flux_accounts = set()
        orphan_fluxes = []
        for f in fluxes:
            if f.key_id:
                acct = f.key_id.split("/")[-1] if "/" in f.key_id else f.key_id
                flux_accounts.add(acct)
                # No need to track orphans at account level — flux without rec is normal

        # Recs without flux is more interesting — these accounts have no variance monitoring
        recs_without_flux = []
        for r in recs:
            if r.key_id:
                acct = r.key_id.split("/")[-1] if "/" in r.key_id else r.key_id
                if acct and acct not in flux_accounts:
                    recs_without_flux.append(r)

        if recs_without_flux and len(recs_without_flux) >= 3:
            findings.append(Finding(
                dimension="completeness",
                severity="info",
                title=f"{len(recs_without_flux)} reconciled accounts have no corresponding flux review",
                detail="These accounts are being reconciled but have no variance analysis set up. "
                       "Flux reviews catch trends and anomalies that reconciliations alone may miss.",
                action="Consider adding flux reviews for key accounts that are reconciled, especially revenue, cash, and material balance sheet accounts.",
                tier="fix_this_quarter",
                affected_tasks=[t.name for t in recs_without_flux[:10]],
            ))

    # --- Flux completion patterns (informational) ---
    flux_complete = [t for t in fluxes if t.prep_status == "COMPLETE"]
    flux_skipped = [t for t in fluxes if t.prep_status in ("SKIPPED", "IMMATERIAL")]
    flux_pending = [t for t in fluxes if t.prep_status == "PENDING"]

    skip_rate = len(flux_skipped) / len(fluxes) * 100 if fluxes else 0
    complete_rate = len(flux_complete) / len(fluxes) * 100 if fluxes else 0

    # High skip rate is actually fine for flux — means low variance
    # But if NOTHING is skipped, they might not be using thresholds effectively
    # Exception: flux tasks from connected reports are pre-filtered by Numeric —
    # they only appear when variance exceeds threshold, so 0% skip is expected.
    flux_from_reports = [t for t in fluxes if t.report_id]
    all_from_reports = len(flux_from_reports) == len(fluxes)

    if skip_rate == 0 and len(fluxes) > 20 and not all_from_reports:
        # Some or all flux tasks are manual — 0% skip suggests thresholds may need tuning
        manual_count = len(fluxes) - len(flux_from_reports)
        findings.append(Finding(
            dimension="hygiene",
            severity="info",
            title=f"All {manual_count} manual flux {'task is' if manual_count == 1 else 'tasks are'} marked as requiring completion",
            detail="Flux tasks are threshold-based — accounts with immaterial variances can be marked as "
                   "immaterial or skipped. If 100% of manual flux tasks are being completed, your thresholds "
                   "may be too sensitive, or the team may not be using the immaterial/skip workflow.",
            action="Review your flux thresholds. Accounts consistently below threshold should be quickly marked immaterial to focus analyst time on meaningful variances.",
            tier="fix_this_quarter",
        ))

    return findings


def analyze_journal_entries(tasks: list, profile: CompanyProfile) -> list:
    """Deep dive on journal entry tasks — these are highest audit risk."""
    findings = []
    jes = [t for t in tasks if t.task_type == "journal_entry"]

    if not jes:
        return findings

    # JEs without descriptions (audit risk)
    je_no_desc = [t for t in jes if not t.description]
    if je_no_desc:
        pct = len(je_no_desc) / len(jes) * 100
        findings.append(Finding(
            dimension="controls",
            severity="critical" if profile.audit_requirement != "none" and pct > 50 else "warning",
            title=f"{len(je_no_desc)} of {len(jes)} journal entries have no description ({pct:.0f}%)",
            detail="Journal entries are the #1 thing auditors ask about. Each JE should describe what it does, why it's needed, and where to find supporting docs. Teams with clean audits typically have descriptions on 100% of their JEs. " +
                   "Example JEs missing descriptions: " + ", ".join(f'"{t.name[:50]}"' for t in je_no_desc[:5]) +
                   (f" ...and {len(je_no_desc) - 5} more" if len(je_no_desc) > 5 else ""),
            action="Add descriptions to every journal entry. Include: (1) what the entry does, (2) how the amount is calculated, (3) what supporting doc to attach.",
            tier="fix_now" if profile.audit_requirement != "none" else "fix_this_close",
            affected_tasks=[t.name for t in je_no_desc],
        ))

    # JEs without category
    je_no_cat = [t for t in jes if not t.properties.get("Category", "").strip()]
    if je_no_cat:
        pct = len(je_no_cat) / len(jes) * 100
        if pct > 30:
            findings.append(Finding(
                dimension="controls",
                severity="warning",
                title=f"{len(je_no_cat)} of {len(jes)} journal entries have no Category ({pct:.0f}%)",
                detail="Uncategorized JEs make it harder to track which accounting areas have proper journal entry controls. " +
                       "Examples: " + ", ".join(f'"{t.name[:50]}"' for t in je_no_cat[:5]),
                action="Assign a Category to each journal entry so your close progress accurately reflects JE completion by area.",
                tier="fix_this_close",
                affected_tasks=[t.name for t in je_no_cat],
            ))

    # JEs where preparer = reviewer (no segregation of duties)
    je_same_person = [t for t in jes if t.prep_assignee and t.review_assignee
                      and t.prep_assignee == t.review_assignee]
    if je_same_person:
        # On solo/small teams, SoD may be impossible — downgrade severity
        if profile.team_tier in ("solo", "small"):
            sod_severity = "info"
            sod_detail = ("Having the same person prepare and review a journal entry is a segregation of duties concern. "
                         f"With a team of {profile.team_size}, full separation may not be feasible for every JE — "
                         "but consider adding a reviewer for your highest-risk entries (material JEs, non-recurring adjustments). "
                         "Examples: " + ", ".join(f'"{t.name[:40]}" ({t.prep_assignee})' for t in je_same_person[:5]))
            sod_action = "For a small team, focus SoD on your highest-risk JEs first. Even having a manager spot-check is better than no separation."
            sod_tier = "fix_this_quarter"
        else:
            sod_severity = "critical" if profile.audit_requirement != "none" else "warning"
            sod_detail = ("Having the same person prepare and review a journal entry is the most common segregation of duties finding in audits. "
                         "It's an easy fix but a significant control gap. "
                         "Examples: " + ", ".join(f'"{t.name[:40]}" ({t.prep_assignee})' for t in je_same_person[:5]))
            sod_action = "Assign different reviewers to these journal entries. No one should review their own work."
            sod_tier = "fix_now"

        findings.append(Finding(
            dimension="controls",
            severity=sod_severity,
            title=f"{len(je_same_person)} journal entr{'ies' if len(je_same_person) != 1 else 'y'} {'have' if len(je_same_person) != 1 else 'has'} the same preparer and reviewer",
            detail=sod_detail,
            action=sod_action,
            tier=sod_tier,
            affected_tasks=[t.name for t in je_same_person],
        ))

    # JEs with no due date
    je_no_due = [t for t in jes if not t.prep_due]
    if je_no_due:
        findings.append(Finding(
            dimension="structure",
            severity="warning",
            title=f"{len(je_no_due)} journal entries have no due date",
            detail="JEs without due dates can't be tracked in the close timeline and may slip through. " +
                   "Examples: " + ", ".join(f'"{t.name[:50]}"' for t in je_no_due[:5]),
            action="Set due dates for all journal entries. They should be due before their corresponding flux review or reporting task.",
            tier="fix_this_close",
            affected_tasks=[t.name for t in je_no_due],
        ))

    # Summary stat for the report
    je_with_reviewer = [t for t in jes if t.review_assignee]
    je_with_desc = [t for t in jes if t.description]
    je_with_cat = [t for t in jes if t.properties.get("Category", "").strip()]

    return findings


# ============================================================
# Feature Adoption Analyzers
# ============================================================

def analyze_je_linking(tasks: list, profile: CompanyProfile) -> list:
    """Check if journal entry tasks are linked to actual ERP journal entries.

    Linked JE tasks (key_type != 'custom') auto-track the journal entry in Numeric,
    pulling status and amounts from the ERP. Unlinked JEs (key_type == 'custom') are
    just manual checkboxes — someone has to remember to mark them done, and there's
    no audit trail connecting the task to the actual entry.
    """
    findings = []
    jes = [t for t in tasks if t.task_type == "journal_entry"]
    if not jes:
        return findings

    unlinked = [t for t in jes if t.key_type == "custom"]
    linked = [t for t in jes if t.key_type != "custom"]

    if unlinked:
        pct = len(unlinked) / len(jes) * 100

        findings.append(Finding(
            dimension="hygiene",
            severity="info",
            title=f"{len(unlinked)} of {len(jes)} journal entries are not linked to ERP records ({pct:.0f}%)",
            detail="Unlinked JE tasks are manual checkboxes — there's no automatic connection to the actual journal entry in your ERP. "
                   "Linked JE tasks auto-track posting status, amounts, and provide a direct audit trail. "
                   "This requires your ERP to be connected to Numeric — if it already is, linking your recurring JEs is one of the biggest time-savers available. "
                   "See: https://help.numeric.io/articles/1645659549-automatically-tracking-journal-entires",
            action="If your ERP is connected, link your recurring monthly JE tasks to their ERP entries. Start with the highest-volume JEs for the biggest payoff.",
            tier="fix_this_quarter",
            affected_tasks=[t.name for t in unlinked[:20]],
        ))

    return findings


def analyze_email_automations(tasks: list, profile: CompanyProfile) -> list:
    """Check for evidence of email automation usage.

    Numeric supports email automations for reminders and follow-ups:
    - Task due date reminders (before/on/after due date)
    - Overdue task follow-ups
    - Close kickoff notifications
    - Department cutoff reminders

    We can't directly detect email automation config from task data, but we can:
    1. Check for reminder/notification tasks (suggests manual process instead of automation)
    2. Look for patterns that indicate automations would help (overdue tasks, many assignees)
    3. Flag the opportunity if the team is large enough to benefit
    """
    findings = []

    # Check for manual reminder tasks — these suggest email automations aren't set up
    reminder_keywords = ["remind", "send email", "notify team", "notify department",
                         "follow up with", "follow-up with", "chase down",
                         "ping someone", "check in with", "cutoff notice", "cutoff notification",
                         "send close calendar", "kick off close", "kickoff email", "send reminder"]
    manual_reminder_tasks = []
    for t in tasks:
        name_lower = t.name.lower()
        desc_lower = (t.description or "").lower()
        combined = name_lower + " " + desc_lower
        for kw in reminder_keywords:
            if kw in combined:
                manual_reminder_tasks.append(t)
                break

    # Large teams benefit most from email automations
    if profile.team_size >= 3:
        if manual_reminder_tasks:
            findings.append(Finding(
                dimension="hygiene",
                severity="info",
                title=f"{len(manual_reminder_tasks)} {'task appears' if len(manual_reminder_tasks) == 1 else 'tasks appear'} to be manual reminders that could be automated",
                detail="These tasks look like manual notification/reminder steps: " +
                       ", ".join(f'"{t.name[:50]}"' for t in manual_reminder_tasks[:5]) +
                       (f" ...and {len(manual_reminder_tasks) - 5} more" if len(manual_reminder_tasks) > 5 else "") +
                       ". Numeric's email automations can handle these automatically — teams that set them up typically eliminate 3-5 manual tasks per close. "
                       "See: https://help.numeric.io/articles/6122174044-using-email-automation",
                action="Set up email automations to replace these manual tasks. Most teams start with: due date reminders (1 day before), "
                       "overdue follow-ups (1 day after), and close kickoff emails.",
                tier="fix_this_quarter",
                affected_tasks=[t.name for t in manual_reminder_tasks],
            ))
        else:
            # No manual reminders found — but also no sign of automation
            # Flag the opportunity for larger teams
            if profile.team_size >= 5:
                findings.append(Finding(
                    dimension="hygiene",
                    severity="info",
                    title="Consider setting up email automations for your team of " + str(profile.team_size),
                    detail="With " + str(profile.team_size) + " people involved in the close, email automations can significantly reduce "
                           "manual coordination. Numeric supports automatic reminders for upcoming due dates, overdue task follow-ups, "
                           "and close kickoff notifications. See https://help.numeric.io/articles/6122174044-using-email-automation",
                    action="Configure email automations: (1) reminder 1 day before task due, (2) escalation 1 day after overdue, "
                           "(3) close kickoff email on Day 1 with each person's task list.",
                    tier="fix_this_quarter",
                ))

    return findings


def analyze_feature_adoption(tasks: list, profile: CompanyProfile) -> list:
    """Check adoption of key Numeric features beyond basic task tracking.

    Features to check:
    - Second reviewer usage (for high-risk tasks)
    - Recurring task patterns (one-off vs recurring setup)
    - Rec/flux linking (are recs connected to GL accounts?)
    - Task type usage (are they using JE and rec types or just custom for everything?)
    """
    findings = []

    # --- Task type adoption: everything as 'custom' is a smell ---
    type_counts = {}
    for t in tasks:
        tt = t.task_type or "unknown"
        type_counts[tt] = type_counts.get(tt, 0) + 1

    custom_count = type_counts.get("custom", 0)
    je_count = type_counts.get("journal_entry", 0)
    rec_count = type_counts.get("rec_prepare_account", 0)
    flux_count = type_counts.get("flux", 0)

    # If many tasks are custom but names suggest they should be JE or rec type
    # For CSV imports, the parser already tried name-matching so only flag strong signals
    if profile.from_csv:
        je_keywords = ["journal entry", " je ", " je:", "reclass je"]
    else:
        je_keywords = ["journal entry", "je ", "book ", "record ", "post ", "accrue ", "reclass"]
    custom_should_be_je = []
    for t in tasks:
        if t.task_type == "custom":
            name_lower = t.name.lower()
            for kw in je_keywords:
                if kw in name_lower:
                    custom_should_be_je.append(t)
                    break

    if custom_should_be_je and len(custom_should_be_je) >= 3:
        findings.append(Finding(
            dimension="completeness",
            severity="info",
            title=f"{len(custom_should_be_je)} custom tasks look like they should be journal entry type",
            detail="These tasks have names suggesting they're journal entries but are created as custom tasks: " +
                   ", ".join(f'"{t.name[:50]}"' for t in custom_should_be_je[:5]) +
                   (f" ...and {len(custom_should_be_je) - 5} more" if len(custom_should_be_je) > 5 else "") +
                   ". Using the journal_entry task type unlocks JE-specific features like auto-tracking, reviewer enforcement, and a cleaner audit trail.",
            action="Recreate these as journal_entry type tasks. It takes a few minutes per task and gives you significantly better controls and tracking.",
            tier="fix_this_quarter",
            affected_tasks=[t.name for t in custom_should_be_je],
        ))

    # --- Recs not linked to GL accounts (skip for CSV — key_type unavailable) ---
    recs = [t for t in tasks if t.task_type == "rec_prepare_account"]
    unlinked_recs = [t for t in recs if t.key_type == "custom"]
    if unlinked_recs and len(unlinked_recs) >= 3 and not profile.from_csv:
        pct = len(unlinked_recs) / len(recs) * 100
        findings.append(Finding(
            dimension="controls",
            severity="info",
            title=f"{len(unlinked_recs)} of {len(recs)} reconciliation tasks are not linked to GL accounts ({pct:.0f}%)",
            detail="Unlinked reconciliations don't pull balances from your ERP. Linked recs auto-populate the account balance, "
                   "reducing manual data entry and ensuring the rec matches what's in the GL. Most teams that link their recs say the auto-populated balances alone save meaningful time each close.",
            action="Link reconciliation tasks to their GL accounts. Start with your highest-volume recs — the time savings compound each month.",
            tier="fix_this_quarter",
            affected_tasks=[t.name for t in unlinked_recs[:15]],
        ))

    return findings


# ============================================================
# Scoring
# ============================================================

DIMENSION_WEIGHTS = {
    "accountability": 0.25,
    "controls": 0.20,
    "completeness": 0.15,
    "structure": 0.15,
    "properties": 0.10,
    "timeline": 0.10,
    "hygiene": 0.05,
}

DIMENSION_LABELS = {
    "accountability": "Accountability",
    "controls": "Controls & Compliance",
    "completeness": "Task Completeness",
    "structure": "Structure & Sequencing",
    "properties": "Property Adoption",
    "timeline": "Timeline",
    "hygiene": "Close Hygiene",
}


def score_dimension(findings: list) -> int:
    """Score 0-100 for a dimension based on its findings.

    Uses diminishing returns — the first critical finding hits hard, but
    subsequent findings of the same severity have less impact. This prevents
    a dimension with many small issues from scoring worse than one with a
    single critical gap.

    Base penalties: critical=20, warning=10, info=3
    Each subsequent finding of the same severity gets 60% of the previous penalty.
    Floor at 10 to avoid impossibly low scores on dimensions with many info findings.
    """
    if not findings:
        return 95  # No issues found = near-perfect

    # Sort by severity so criticals are counted first (full penalty)
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 3))

    penalty = 0
    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    base_penalties = {"critical": 20, "warning": 10, "info": 3}
    decay = 0.6  # each subsequent finding of same severity gets 60% of previous

    for f in sorted_findings:
        count = severity_counts.get(f.severity, 0)
        base = base_penalties.get(f.severity, 3)
        this_penalty = base * (decay ** count)
        penalty += this_penalty
        severity_counts[f.severity] = count + 1

    return max(10, int(100 - penalty))


def maturity_stage(score: float) -> str:
    """Map score to accounting-native maturity label."""
    if score >= 85:
        return "Controlled Close"
    elif score >= 70:
        return "Audit-Ready"
    elif score >= 55:
        return "Closing In"
    elif score >= 40:
        return "Adjusting"
    else:
        return "Establishing"


STAGE_DESCRIPTIONS = {
    "Controlled Close": "Your process is tight, documented, and defensible. This is what best-in-class looks like.",
    "Audit-Ready": "Strong controls, clear ownership. A few targeted moves and you're there.",
    "Closing In": "Momentum is building. The gaps are known and fixable.",
    "Adjusting": "Framework is forming. A few targeted tightenings make a big difference.",
    "Establishing": "Early-stage process — clear opportunities to build foundational controls.",
}

STAGE_COLORS = {
    "Controlled Close": "#22c55e",
    "Audit-Ready": "#3b82f6",
    "Closing In": "#f59e0b",
    "Adjusting": "#f97316",
    "Establishing": "#b45309",
}


# ============================================================
# HTML Report
# ============================================================

def _fix_plural(text: str) -> str:
    """Fix '1 tasks' → '1 task' and similar singular/plural mismatches."""
    text = re.sub(r'\b1 tasks\b', '1 task', text)
    text = re.sub(r'\b1 entries\b', '1 entry', text)
    text = re.sub(r'\b1 issues\b', '1 issue', text)
    text = re.sub(r'\b1 users\b', '1 user', text)
    return text


def generate_html(profile: CompanyProfile, tasks: list, all_findings: list, dim_scores: dict, total_score: float, heatmap_red: int = 9, goals: list = None) -> str:
    stage = maturity_stage(total_score)
    stage_color = STAGE_COLORS.get(stage, "#6b7280")
    stage_desc = STAGE_DESCRIPTIONS.get(stage, "")

    # Build task name → URL lookup for deep links
    task_url_lookup = {}
    for t in tasks:
        if t.url:
            task_url_lookup[t.name] = t.url

    severity_icons = {"critical": "&#9888;", "warning": "&#9679;", "info": "&#8505;"}
    severity_colors = {"critical": "#ef4444", "warning": "#f59e0b", "info": "#3b82f6"}
    tier_labels = {"fix_now": "Fix Now", "fix_this_close": "Fix This Close", "fix_this_quarter": "Fix This Quarter"}

    # Build flux summary data
    flux_tasks = [t for t in tasks if t.task_type == "flux"]
    flux_summary = None
    if flux_tasks:
        flux_complete = sum(1 for t in flux_tasks if t.prep_status == "COMPLETE")
        flux_skipped = sum(1 for t in flux_tasks if t.prep_status in ("SKIPPED", "IMMATERIAL"))
        flux_pending = sum(1 for t in flux_tasks if t.prep_status == "PENDING")
        flux_with_rev = sum(1 for t in flux_tasks if t.review_assignee)
        flux_with_cat = sum(1 for t in flux_tasks if t.properties.get("Category", "").strip())
        flux_with_prep = sum(1 for t in flux_tasks if t.prep_assignee)
        flux_summary = {
            "total": len(flux_tasks),
            "complete": flux_complete,
            "skipped": flux_skipped,
            "pending": flux_pending,
            "with_reviewer": flux_with_rev,
            "with_category": flux_with_cat,
            "with_preparer": flux_with_prep,
            "pct_of_total": len(flux_tasks) / len(tasks) * 100,
        }

    # Build JE summary data
    je_tasks = [t for t in tasks if t.task_type == "journal_entry"]
    je_summary = None
    if je_tasks:
        je_with_rev = sum(1 for t in je_tasks if t.review_assignee)
        je_with_desc = sum(1 for t in je_tasks if t.description)
        je_with_cat = sum(1 for t in je_tasks if t.properties.get("Category", "").strip())
        je_same_person = sum(1 for t in je_tasks if t.prep_assignee and t.review_assignee and t.prep_assignee == t.review_assignee)
        je_summary = {
            "total": len(je_tasks),
            "with_reviewer": je_with_rev,
            "with_description": je_with_desc,
            "with_category": je_with_cat,
            "same_preparer_reviewer": je_same_person,
        }

    # Build workload heatmap data
    person_day = defaultdict(lambda: defaultdict(int))
    for t in tasks:
        if t.prep_assignee and t.prep_due:
            person_day[t.prep_assignee][t.prep_due] += 1

    prep_counts = Counter(t.prep_assignee for t in tasks if t.prep_assignee)
    top_people = [p for p, _ in prep_counts.most_common(10)]
    all_dates = sorted(set(t.prep_due for t in tasks if t.prep_due))

    # Build property adoption data
    prop_data = []
    for tg in profile.tag_groups:
        tg_name = tg.get("name", "")
        if not tg_name:
            continue
        populated = sum(1 for t in tasks if t.properties.get(tg_name, "").strip())
        pct = populated / len(tasks) * 100 if tasks else 0
        status = "good" if pct >= 70 else "partial" if pct >= 20 else "low" if pct > 0 else "empty"
        status_color = {"good": "#22c55e", "partial": "#f59e0b", "low": "#ef4444", "empty": "#d1d5db"}.get(status)
        prop_data.append((tg_name, populated, len(tasks), pct, status, status_color, tg.get("is_required", False)))

    # Group findings by tier
    # Sort findings: goal-relevant ones first within each tier
    goal_dims = set()
    if goals:
        goal_dim_map = {
            "controls": {"controls", "accountability"},
            "workload": {"accountability", "structure"},
            "hygiene": {"hygiene", "completeness"},
            "features": {"controls", "hygiene"},
            "timeline": {"timeline", "structure"},
        }
        for g in (goals or []):
            goal_dims.update(goal_dim_map.get(g, set()))

    def goal_sort_key(f):
        return (0 if f.dimension in goal_dims else 1, {"critical": 0, "warning": 1, "info": 2}.get(f.severity, 3))

    fix_now = sorted([f for f in all_findings if f.tier == "fix_now"], key=goal_sort_key)
    fix_close = sorted([f for f in all_findings if f.tier == "fix_this_close"], key=goal_sort_key)
    fix_quarter = sorted([f for f in all_findings if f.tier == "fix_this_quarter"], key=goal_sort_key)

    # Executive summary — build a 2-sentence narrative
    criticals = [f for f in all_findings if f.severity == "critical"]
    warnings = [f for f in all_findings if f.severity == "warning"]

    # Sentence 1: biggest areas to improve (deduplicated, properly cased)
    top_issues = []
    seen_dims = set()
    for f in (criticals + warnings)[:6]:
        # Skip if we already have a finding from this dimension
        if f.dimension in seen_dims:
            continue
        seen_dims.add(f.dimension)
        t = f.title
        if " — " in t:
            t = t.split(" — ")[1]
        # Shorten verbose titles and fix grammar
        t = t.replace("have no reviewer", "lack reviewers").replace("have no preparer", "are unassigned").replace("have no description", "lack descriptions")
        t = _fix_plural(t)
        top_issues.append(t.strip())
        if len(top_issues) >= 3:
            break

    if top_issues:
        # Professional sentence case — courteous and clear
        issues_formatted = [i[0].lower() + i[1:] if i else i for i in top_issues]
        if len(issues_formatted) > 2:
            exec_sentence_1 = f"The biggest opportunities are {issues_formatted[0]}, {issues_formatted[1]}, and {issues_formatted[2]}."
        elif len(issues_formatted) == 2:
            exec_sentence_1 = f"The biggest opportunities are {issues_formatted[0]} and {issues_formatted[1]}."
        else:
            exec_sentence_1 = f"The biggest opportunity is {issues_formatted[0]}."
    else:
        exec_sentence_1 = "Your close checklist is in strong shape — no critical issues found."

    # Sentence 2: concrete next step (courteous, never repeat sentence 1 content)
    if fix_now:
        # All fix_now items are quick wins — summarize count and point to section
        exec_sentence_2 = f"All {len(fix_now)} item{'s' if len(fix_now) != 1 else ''} in the Fix Now section below can be addressed in under 10 minutes each."
    elif fix_close:
        exec_sentence_2 = f"We'd recommend focusing on the {len(fix_close)} items in the Fix This Close section to move toward best-in-class."
    else:
        exec_sentence_2 = "No urgent actions needed — the strategic improvements below will help you continue to refine your process."

    task_type_counts = Counter(t.task_type for t in tasks)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Close Checklist Diagnostic — {profile.workspace_name}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.6; font-size: 12px; }}
.container {{ max-width: 960px; margin: 0 auto; padding: 32px 24px; }}
h1 {{ font-size: 24px; font-weight: 700; margin-bottom: 4px; }}
h2 {{ font-size: 18px; font-weight: 600; margin: 32px 0 16px; padding-bottom: 8px; border-bottom: 2px solid #e2e8f0; }}
h3 {{ font-size: 15px; font-weight: 600; margin: 16px 0 8px; }}
.header {{ text-align: center; margin-bottom: 8px; }}
.subtitle {{ color: #64748b; font-size: 13px; margin-top: 2px; }}
.sc-details.collapsed {{ display: none; }}
.exec-summary {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 16px; font-size: 13px; }}
.exec-summary p {{ margin-bottom: 6px; }}
.exec-summary strong {{ color: #0f172a; }}
.profile-toggle {{ cursor: pointer; user-select: none; color: #64748b; font-size: 12px; font-weight: 500; display: flex; align-items: center; gap: 4px; margin-bottom: 16px; }}
.profile-toggle:hover {{ color: #1e293b; }}
.profile-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px 20px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 12px 16px; margin-bottom: 16px; font-size: 11px; }}
.profile-grid.collapsed {{ display: none; }}
.profile-item {{ display: flex; justify-content: space-between; padding: 2px 0; }}
.profile-label {{ color: #94a3b8; }}
.profile-value {{ font-weight: 600; color: #475569; }}
.score-bar-bg {{ height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; }}
.score-bar {{ height: 100%; border-radius: 3px; transition: width 0.3s; }}
.finding {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px 20px; margin-bottom: 12px; border-left: 4px solid; }}
.finding-header {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.finding-severity {{ font-size: 16px; }}
.finding-title {{ font-weight: 600; font-size: 14px; }}
.finding-detail {{ font-size: 13px; color: #475569; margin-bottom: 8px; }}
.finding-action {{ font-size: 13px; color: #1e293b; background: #f1f5f9; padding: 8px 12px; border-radius: 4px; }}
.finding-action strong {{ color: #0f172a; }}
.tier-header {{ display: flex; align-items: center; gap: 12px; margin: 32px 0 16px; padding: 12px 16px; border-radius: 10px; }}
.tier-badge {{ font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }}
.tier-fix_now .tier-badge {{ color: #dc2626; }}
.tier-fix_this_close .tier-badge {{ color: #d97706; }}
.tier-fix_this_quarter .tier-badge {{ color: #2563eb; }}
.tier-fix_now {{ background: #fef2f2; border: 1px solid #fecaca; }}
.tier-fix_this_close {{ background: #fffbeb; border: 1px solid #fde68a; }}
.tier-fix_this_quarter {{ background: #eff6ff; border: 1px solid #bfdbfe; }}
.tier-count {{ color: #64748b; font-size: 14px; font-weight: 500; }}
table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
th {{ text-align: left; padding: 8px 6px; background: #f8fafc; border-bottom: 2px solid #e2e8f0; font-weight: 600; color: #64748b; font-size: 11px; text-transform: uppercase; }}
td {{ padding: 6px; border-bottom: 1px solid #f1f5f9; }}
.heatmap-cell {{ text-align: center; font-size: 11px; font-weight: 500; border-radius: 3px; min-width: 28px; }}
.prop-bar {{ display: inline-block; height: 6px; border-radius: 3px; }}
.prop-status {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; }}
.empty-tier {{ color: #94a3b8; font-style: italic; font-size: 13px; padding: 12px 0; }}
.affected-tasks {{ margin-top: 8px; font-size: 12px; }}
.affected-tasks summary {{ cursor: pointer; color: #64748b; font-weight: 500; }}
.affected-tasks summary:hover {{ color: #1e293b; }}
.affected-tasks ul {{ margin: 6px 0 0 20px; color: #475569; }}
.affected-tasks li {{ margin: 2px 0; }}
.task-link {{ color: #6366f1; text-decoration: none; }}
.task-link:hover {{ text-decoration: underline; color: #4f46e5; }}
.nav {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #e2e8f0; padding: 8px 24px; margin: 0 -24px 24px; z-index: 10; display: flex; justify-content: center; gap: 20px; font-size: 12px; }}
.nav a {{ color: #64748b; text-decoration: none; font-weight: 500; padding: 4px 0; }}
.nav a:hover {{ color: #1e293b; }}
.tier-section {{ margin-bottom: 8px; }}
.tier-toggle {{ cursor: pointer; user-select: none; }}
.tier-toggle:hover .tier-badge {{ opacity: 0.8; }}
.tier-body {{ overflow: hidden; }}
.tier-body.collapsed {{ display: none; }}
@media print {{
  .nav {{ display: none !important; }}
  .tier-body.collapsed {{ display: block !important; }}
  .sc-details.collapsed {{ display: block !important; }}
  .profile-grid.collapsed {{ display: block !important; }}
  .sc-toggle {{ display: none !important; }}
  .profile-toggle {{ display: none !important; }}
  .tier-toggle {{ pointer-events: none; }}
  #hm-threshold {{ display: none !important; }}
  body {{ font-size: 11px; background: #fff; }}
  .container {{ max-width: 100%; padding: 0; }}
  .finding {{ break-inside: avoid; }}
  h2 {{ break-after: avoid; }}
  .tier-header {{ break-after: avoid; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <div class="subtitle">{profile.workspace_name} &middot; {profile.period_slug} &middot; {len(tasks)} tasks</div>
  <div style="font-size:11px;color:#94a3b8;margin-top:6px;line-height:1.5;font-style:italic">Snapshot of one close period. This reflects the state of your checklist for {profile.period_slug}, not the overall quality of your close.</div>
</div>

<div id="scorecard" style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:16px 20px;margin-bottom:12px">
  <div style="display:flex;align-items:center;gap:16px;margin-bottom:4px">
    <div style="font-size:42px;font-weight:800;color:{stage_color};line-height:1">{total_score:.0f}</div>
    <div>
      <div style="display:inline-block;background:{stage_color}12;color:{stage_color};border:1.5px solid {stage_color}40;padding:3px 12px;border-radius:10px;font-size:12px;font-weight:700">{stage}</div>
      <div style="font-size:12px;color:#64748b;margin-top:3px">{stage_desc}</div>
    </div>
  </div>
  <div class="sc-toggle" onclick="this.nextElementSibling.classList.toggle('collapsed');this.querySelector('span').textContent=this.nextElementSibling.classList.contains('collapsed')?'&#9656;':'&#9662;'" style="cursor:pointer;font-size:11px;color:#94a3b8;font-weight:500;padding:6px 0 0;user-select:none">
    <span>&#9656;</span> Score breakdown
  </div>
  <div class="sc-details collapsed" style="margin-top:8px">
"""

    # Inline scorecard dimensions
    for dim in ["accountability", "controls", "completeness", "structure", "properties", "timeline", "hygiene"]:
        s = dim_scores.get(dim, 95)
        color = "#22c55e" if s >= 80 else "#f59e0b" if s >= 60 else "#ef4444"
        label = DIMENSION_LABELS.get(dim, dim)
        weight = int(DIMENSION_WEIGHTS.get(dim, 0) * 100)
        html += f"""    <div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px">
      <span style="width:130px;color:#475569;font-weight:500">{label}</span>
      <span style="width:32px;color:#94a3b8;font-size:11px;text-align:center">{weight}%</span>
      <div style="flex:1;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden"><div style="height:100%;width:{s}%;background:{color};border-radius:3px"></div></div>
      <span style="width:28px;text-align:right;font-weight:700;font-size:13px;color:{color}">{s}</span>
    </div>
"""

    html += f"""  </div>
</div>

<div class="nav">
  <a href="#fix-now">Fix Now ({len(fix_now)})</a>
  <a href="#fix-this-close">Fix This Close ({len(fix_close)})</a>
  <a href="#fix-this-quarter">Fix This Quarter ({len(fix_quarter)})</a>
  <a href="#heatmap">Workload</a>
  <a href="#" onclick="window.print();return false" style="color:#7036FF;border:1px solid #7036FF;padding:2px 10px;border-radius:4px;font-weight:600">Export PDF</a>
</div>

<div class="exec-summary">
  <p style="font-size:14px;line-height:1.5;margin-bottom:8px">{exec_sentence_1} {exec_sentence_2}</p>
  <p style="color:#64748b">{len(criticals)} critical &middot; {len(warnings)} warning &middot; {len(all_findings) - len(criticals) - len(warnings)} informational</p>
</div>
"""

    # --- Goal-based personalization ---
    goals = goals or []
    GOAL_CONFIG = {
        "controls": {
            "label": "Controls & Audit Readiness",
            "dims": ["controls", "accountability"],
            "intro": "You asked about audit readiness. Here's what matters most for your auditors:",
        },
        "workload": {
            "label": "Workload & Bottlenecks",
            "dims": ["accountability", "structure"],
            "intro": "You flagged workload as a concern. Here's where the pressure is:",
        },
        "hygiene": {
            "label": "Task Hygiene",
            "dims": ["hygiene", "completeness"],
            "intro": "You want cleaner task data. These are the biggest hygiene gaps:",
        },
        "features": {
            "label": "Feature Adoption",
            "dims": ["controls", "hygiene"],
            "intro": "You're looking to get more from Numeric. Here's what's underused:",
        },
        "timeline": {
            "label": "Timeline Optimization",
            "dims": ["timeline", "structure"],
            "intro": "You want to close faster. Here's where you can find days:",
        },
    }

    sev_order = {"critical": 0, "warning": 1, "info": 2}
    focus_goals = [g for g in goals if g in GOAL_CONFIG and g != "health_check"]
    if focus_goals:
        html += '<div style="margin-bottom:16px">\n'
        for goal_key in focus_goals:
            gc = GOAL_CONFIG[goal_key]
            goal_findings = [f for f in all_findings if f.dimension in gc["dims"]]
            goal_findings.sort(key=lambda f: sev_order.get(f.severity, 3))
            top = goal_findings[:3]

            html += f"""<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:14px 18px;margin-bottom:8px;border-left:3px solid #7036FF">
  <div style="font-size:12px;font-weight:700;color:#7036FF;margin-bottom:6px">{gc["label"]}</div>
  <div style="font-size:12px;color:#64748b;margin-bottom:8px">{gc["intro"]}</div>
"""
            if top:
                for f in top:
                    scolor = severity_colors.get(f.severity, "#6b7280")
                    sicon = severity_icons.get(f.severity, "")
                    html += f'  <div style="font-size:12px;padding:3px 0"><span style="color:{scolor}">{sicon}</span> {f.title}</div>\n'
            else:
                html += '  <div style="font-size:12px;color:#22c55e;padding:3px 0">No issues found in this area.</div>\n'
            html += '</div>\n'
        html += '</div>\n'

    html += f"""
<div class="profile-toggle" onclick="this.nextElementSibling.classList.toggle('collapsed');this.querySelector('span').textContent=this.nextElementSibling.classList.contains('collapsed')?'&#9656;':'&#9662;'" style="margin-bottom:16px">
  <span>&#9656;</span> Workspace profile
</div>
<div class="profile-grid collapsed">
  <div class="profile-item"><span class="profile-label">Team</span><span class="profile-value">{profile.team_size} ({profile.team_tier})</span></div>
  <div class="profile-item"><span class="profile-label">Entities</span><span class="profile-value">{profile.entity_count}</span></div>
  <div class="profile-item"><span class="profile-label">Close window</span><span class="profile-value">{profile.close_window_days}d</span></div>
  <div class="profile-item"><span class="profile-label">Industry</span><span class="profile-value">{profile.industry or "—"}</span></div>
  <div class="profile-item"><span class="profile-label">Audit</span><span class="profile-value">{profile.audit_requirement or "—"}</span></div>
  <div class="profile-item"><span class="profile-label">Target</span><span class="profile-value">{profile.target_close_days}d</span></div>
  <div class="profile-item"><span class="profile-label">Tasks</span><span class="profile-value">{task_type_counts.get("custom", 0)} task, {task_type_counts.get("journal_entry", 0)} JE, {task_type_counts.get("rec_prepare_account", 0)} rec, {task_type_counts.get("flux", 0)} flux</span></div>
  <div class="profile-item"><span class="profile-label">Properties</span><span class="profile-value">{len(profile.tag_groups)} tag groups</span></div>
  <div class="profile-item"><span class="profile-label">License</span><span class="profile-value">{profile.license_tier or "—"}</span></div>
</div>
"""

    # Task type breakdown panels (Flux + JE)
    if flux_summary or je_summary:
        html += '\n<h2>Task Type Deep Dive</h2>\n'
        html += '<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:24px">\n'

        if flux_summary:
            fs = flux_summary
            rev_pct = fs["with_reviewer"] / fs["total"] * 100
            cat_pct = fs["with_category"] / fs["total"] * 100
            html += f"""<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px">
  <h3 style="margin:0 0 12px;font-size:14px">Flux Analysis — {fs["total"]} tasks ({fs["pct_of_total"]:.0f}% of checklist)</h3>
  <div style="font-size:12px;color:#64748b;margin-bottom:12px">Flux tasks are threshold-based — they only require completion when variance exceeds materiality. Low completion or high skip rates are normal and healthy.</div>
  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:13px">
    <div><span style="font-weight:600;color:#22c55e">{fs["complete"]}</span> completed</div>
    <div><span style="font-weight:600;color:#64748b">{fs["skipped"]}</span> skipped/immaterial</div>
    <div><span style="font-weight:600;color:#f59e0b">{fs["pending"]}</span> pending</div>
  </div>
  <div style="margin-top:12px;font-size:12px;display:grid;grid-template-columns:1fr 1fr;gap:4px">
    <div>Reviewer assigned: <strong>{rev_pct:.0f}%</strong></div>
    <div>Category tagged: <strong>{cat_pct:.0f}%</strong></div>
  </div>
</div>\n"""

        if je_summary:
            js = je_summary
            rev_pct = js["with_reviewer"] / js["total"] * 100
            desc_pct = js["with_description"] / js["total"] * 100
            cat_pct = js["with_category"] / js["total"] * 100
            html += f"""<div style="background:#fff;border:1px solid #e2e8f0;border-radius:8px;padding:16px 20px">
  <h3 style="margin:0 0 12px;font-size:14px">Journal Entries — {js["total"]} tasks</h3>
  <div style="font-size:12px;color:#64748b;margin-bottom:12px">JEs are the highest-audit-risk task type. Every JE needs a reviewer, description, and category for proper controls.</div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:13px">
    <div>Reviewer assigned: <strong style="color:{"#22c55e" if rev_pct >= 80 else "#ef4444"}">{rev_pct:.0f}%</strong></div>
    <div>Has description: <strong style="color:{"#22c55e" if desc_pct >= 80 else "#ef4444"}">{desc_pct:.0f}%</strong></div>
    <div>Category tagged: <strong style="color:{"#22c55e" if cat_pct >= 80 else "#f59e0b"}">{cat_pct:.0f}%</strong></div>
    <div>Same preparer/reviewer: <strong style="color:{"#ef4444" if js["same_preparer_reviewer"] > 0 else "#22c55e"}">{js["same_preparer_reviewer"]}</strong></div>
  </div>
</div>\n"""

        html += '</div>\n'

    # Findings by tier
    for tier_key, tier_findings, tier_label_text in [
        ("fix_now", fix_now, "Fix Now"),
        ("fix_this_close", fix_close, "Fix This Close"),
        ("fix_this_quarter", fix_quarter, "Fix This Quarter"),
    ]:
        tier_id = tier_key.replace("_", "-")
        arrow_down = "&#9662;"
        arrow_right = "&#9656;"
        html += f"""
<div class="tier-section" id="{tier_id}">
<div class="tier-header tier-{tier_key} tier-toggle" onclick="var b=this.nextElementSibling;b.classList.toggle('collapsed');this.querySelector('.tier-arrow').innerHTML=b.classList.contains('collapsed')?'{arrow_right}':'{arrow_down}'">
  <span class="tier-badge">{tier_label_text}</span>
  <span class="tier-count">{len(tier_findings)} finding{'s' if len(tier_findings) != 1 else ''}</span>
  <span class="tier-arrow" style="color:#94a3b8;font-size:14px">{arrow_right}</span>
</div>
<div class="tier-body collapsed">
"""
        if not tier_findings:
            html += '<div class="empty-tier">No findings in this tier.</div>\n'
        for f in tier_findings:
            scolor = severity_colors.get(f.severity, "#6b7280")
            sicon = severity_icons.get(f.severity, "")
            html += f"""<div class="finding" style="border-left-color:{scolor}">
  <div class="finding-header">
    <span class="finding-severity" style="color:{scolor}">{sicon}</span>
    <span class="finding-title">{_fix_plural(f.title)}</span>
  </div>
  <div class="finding-detail">{_fix_plural(f.detail).replace(chr(10) + '• ', '<br>&bull; ').replace(chr(10), '<br>')}</div>
"""
            if f.action:
                html += f'  <div class="finding-action"><strong>Action:</strong> {_fix_plural(f.action)}</div>\n'
            if f.affected_tasks:
                total = len(f.affected_tasks)
                show_limit = 10
                html += f'  <details class="affected-tasks"><summary>Affected tasks ({total})</summary><ul>\n'
                for tname in f.affected_tasks[:show_limit]:
                    url = task_url_lookup.get(tname, "")
                    if url:
                        html += f'    <li><a href="{url}" target="_blank" class="task-link">{tname}</a></li>\n'
                    else:
                        html += f'    <li>{tname}</li>\n'
                if total > show_limit:
                    html += f'    <li><em>...and {total - show_limit} more</em></li>\n'
                html += '  </ul></details>\n'
            html += "</div>\n"
        html += "</div>\n</div>\n"  # close tier-body and tier-section

    # Workload heatmap
    if top_people and all_dates:
        html += f'\n<h2 id="heatmap" style="display:flex;align-items:center;justify-content:space-between">Workload Distribution<label style="font-size:11px;font-weight:500;color:#64748b;display:flex;align-items:center;gap:6px">Red threshold <input type="number" id="hm-threshold" value="{heatmap_red}" min="2" max="99" style="width:48px;padding:3px 6px;border:1px solid #ddd;border-radius:4px;font-size:12px;text-align:center"> tasks/day</label></h2>\n'
        html += '<div style="overflow-x:auto"><table id="hm-table">\n<tr><th>Person</th><th>Total</th>'

        # Show abbreviated dates
        display_dates = all_dates[:20] if len(all_dates) > 20 else all_dates
        for d in display_dates:
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                html += f'<th style="text-align:center;font-size:10px">{dt.strftime("%m/%d")}</th>'
            except ValueError:
                html += f'<th style="text-align:center;font-size:10px">{d[-5:]}</th>'
        html += "</tr>\n"

        # Aggregate row: total tasks per day across ALL assignees (not just top 10)
        day_totals = defaultdict(int)
        for person in person_day:
            for d in display_dates:
                day_totals[d] += person_day[person][d]
        grand_total = sum(day_totals[d] for d in display_dates)
        html += f'<tr style="border-bottom:2px solid #e2e8f0;background:#f8fafc"><td style="font-weight:700">All assignees</td><td><strong>{grand_total}</strong></td>'
        for d in display_dates:
            dt = day_totals[d]
            html += f'<td class="heatmap-cell" data-count="{dt}" style="background:#f1f5f9;color:#334155;font-weight:600">{dt if dt > 0 else ""}</td>'
        html += "</tr>\n"

        for person in top_people:
            total = prep_counts.get(person, 0)
            html += f"<tr><td>{person}</td><td><strong>{total}</strong></td>"
            for d in display_dates:
                count = person_day[person][d]
                amber_threshold = max(4, heatmap_red // 2)
                if count == 0:
                    bg = "#f8fafc"
                    fg = "#cbd5e1"
                elif count <= 3:
                    bg = "#dbeafe"
                    fg = "#1e40af"
                elif count < heatmap_red:
                    bg = "#fef3c7"
                    fg = "#92400e"
                else:
                    bg = "#fecaca"
                    fg = "#991b1b"
                html += f'<td class="heatmap-cell" data-count="{count}" style="background:{bg};color:{fg}">{count if count > 0 else ""}</td>'
            html += "</tr>\n"

        html += "</table></div>\n"

    # Property adoption
    if prop_data:
        html += '\n<h2 id="properties">Property Adoption</h2>\n'
        html += "<table>\n<tr><th>Property</th><th>Required</th><th>Populated</th><th>Rate</th><th>Status</th></tr>\n"
        for name, pop, total, pct, status, color, required in prop_data:
            req_text = "Yes" if required else ""
            html += f'<tr><td>{name}</td><td>{req_text}</td><td>{pop} / {total}</td>'
            html += f'<td><div style="display:flex;align-items:center;gap:6px"><div style="width:60px;height:6px;background:#e2e8f0;border-radius:3px;overflow:hidden"><div style="width:{pct}%;height:100%;background:{color};border-radius:3px"></div></div>{pct:.0f}%</div></td>'
            html += f'<td><span class="prop-status" style="background:{color}"></span></td></tr>\n'
        html += "</table>\n"

    html += """
</div>
<script>
// Auto-expand tier when navigating via anchor link or nav click
document.querySelectorAll('.nav a').forEach(a => {
  a.addEventListener('click', function(e) {
    const id = this.getAttribute('href').substring(1);
    const section = document.getElementById(id);
    if (section) {
      const body = section.querySelector('.tier-body');
      const arrow = section.querySelector('.tier-arrow');
      if (body && body.classList.contains('collapsed')) {
        body.classList.remove('collapsed');
        if (arrow) arrow.innerHTML = '&#9662;';
      }
    }
  });
});
// Handle direct URL hash on load
if (window.location.hash) {
  const section = document.querySelector(window.location.hash);
  if (section) {
    const body = section.querySelector('.tier-body');
    const arrow = section.querySelector('.tier-arrow');
    if (body && body.classList.contains('collapsed')) {
      body.classList.remove('collapsed');
      if (arrow) arrow.innerHTML = '&#9662;';
    }
  }
}

// Heatmap threshold recolor
const hmInput = document.getElementById('hm-threshold');
if (hmInput) {
  hmInput.addEventListener('change', function() {
    const red = parseInt(this.value) || 9;
    document.querySelectorAll('#hm-table .heatmap-cell').forEach(cell => {
      const c = parseInt(cell.dataset.count) || 0;
      let bg, fg;
      if (c === 0) { bg='#f8fafc'; fg='#cbd5e1'; }
      else if (c <= 3) { bg='#dbeafe'; fg='#1e40af'; }
      else if (c < red) { bg='#fef3c7'; fg='#92400e'; }
      else { bg='#fecaca'; fg='#991b1b'; }
      cell.style.background = bg;
      cell.style.color = fg;
    });
  });
}
</script>
</body>
</html>"""

    return html


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Close Checklist Diagnostic")
    # Mode 1: API data (workspace context JSON + tasks TSV)
    parser.add_argument("--workspace-context", help="Path to workspace context JSON")
    parser.add_argument("--tasks", help="Path to tasks TSV file")
    # Mode 2: CSV export
    parser.add_argument("--csv", help="Path to Numeric CSV checklist export")
    # Common arguments
    parser.add_argument("--industry", default="", help="Industry")
    parser.add_argument("--audit", default="none", help="Audit requirement")
    parser.add_argument("--target-close", type=int, default=0, help="Target close in business days")
    parser.add_argument("--current-close", type=int, default=0, help="Self-reported current close in business days")
    parser.add_argument("--outsourced", default="{}", help="Outsourced functions JSON")
    parser.add_argument("--secondary-book", default="no", help="Secondary book yes/no")
    parser.add_argument("--workspace-name", default="", help="Workspace display name")
    parser.add_argument("--goals", default="", help="Comma-separated focus areas: health_check,controls,workload,hygiene,features,timeline")
    parser.add_argument("--heatmap-red", type=int, default=9, help="Heatmap red threshold (tasks per person per day)")
    parser.add_argument("--output", required=True, help="Output HTML path")
    args = parser.parse_args()

    if args.csv:
        # CSV export mode
        profile, tasks = parse_csv_export(args.csv)
        profile.workspace_name = args.workspace_name or "CSV Import"
        # Derive period slug from filename or earliest due date
        csv_basename = os.path.splitext(os.path.basename(args.csv))[0]
        if not profile.period_slug:
            # Try to extract month/year from due dates
            dues = sorted(set(t.prep_due for t in tasks if t.prep_due))
            if dues:
                try:
                    d = datetime.strptime(dues[len(dues)//2], "%Y-%m-%d")  # median due date
                    profile.period_slug = d.strftime("%b-%Y").lower()
                except ValueError:
                    profile.period_slug = csv_basename
    elif args.workspace_context and args.tasks:
        # API data mode
        with open(args.workspace_context) as f:
            ctx_raw = json.load(f)
            if isinstance(ctx_raw, list) and ctx_raw and "text" in ctx_raw[0]:
                ctx = json.loads(ctx_raw[0]["text"])
            else:
                ctx = ctx_raw

        with open(args.tasks) as f:
            tasks_raw = f.read()
            if tasks_raw.startswith("["):
                try:
                    data = json.loads(tasks_raw)
                    if isinstance(data, list) and data and "text" in data[0]:
                        tasks_raw = data[0]["text"]
                except json.JSONDecodeError:
                    pass

        profile = parse_workspace_context(ctx)
        profile.workspace_name = args.workspace_name or profile.workspace_key
        tasks = parse_tasks(tasks_raw, profile)
    else:
        parser.error("Provide either --csv or both --workspace-context and --tasks")

    profile.industry = args.industry
    profile.audit_requirement = args.audit.lower()
    profile.target_close_days = args.target_close
    profile.current_close_days = args.current_close
    profile.secondary_book = args.secondary_book.lower() == "yes"
    try:
        profile.outsourced = json.loads(args.outsourced)
    except json.JSONDecodeError:
        profile.outsourced = {}

    print(f"Parsed {len(tasks)} tasks for {profile.workspace_key} / {profile.period_slug}")
    print(f"Profile: {profile.team_size} assignees, {profile.entity_count} entities, {profile.close_window_days} day close")

    # Run analyzers
    all_findings = []
    all_findings.extend(analyze_accountability(tasks, profile))
    all_findings.extend(analyze_controls(tasks, profile))
    all_findings.extend(analyze_completeness(tasks, profile))
    all_findings.extend(analyze_miscategorization(tasks, profile))
    all_findings.extend(analyze_structure(tasks, profile))
    all_findings.extend(analyze_dependencies(tasks, profile))
    all_findings.extend(analyze_flux_tasks(tasks, profile))
    all_findings.extend(analyze_journal_entries(tasks, profile))
    all_findings.extend(analyze_properties(tasks, profile))
    all_findings.extend(analyze_timeline(tasks, profile))
    all_findings.extend(analyze_hygiene(tasks, profile))
    if not profile.from_csv:  # CSV exports don't include key_type — all JEs look unlinked
        all_findings.extend(analyze_je_linking(tasks, profile))
    all_findings.extend(analyze_email_automations(tasks, profile))
    all_findings.extend(analyze_feature_adoption(tasks, profile))
    all_findings.extend(analyze_late_submissions(tasks, profile))
    all_findings.extend(analyze_pre_close_opportunities(tasks, profile))

    print(f"Found {len(all_findings)} findings: "
          f"{sum(1 for f in all_findings if f.severity == 'critical')} critical, "
          f"{sum(1 for f in all_findings if f.severity == 'warning')} warning, "
          f"{sum(1 for f in all_findings if f.severity == 'info')} info")

    # Score
    dim_findings = defaultdict(list)
    for f in all_findings:
        dim_findings[f.dimension].append(f)

    dim_scores = {}
    for dim in DIMENSION_WEIGHTS:
        dim_scores[dim] = score_dimension(dim_findings.get(dim, []))

    total_score = sum(dim_scores[d] * DIMENSION_WEIGHTS[d] for d in DIMENSION_WEIGHTS)
    stage = maturity_stage(total_score)
    print(f"Overall: {total_score:.0f}/100 — {stage}")

    # Generate HTML
    heatmap_red = args.heatmap_red
    goals = [g.strip() for g in args.goals.split(",") if g.strip()]
    html = generate_html(profile, tasks, all_findings, dim_scores, total_score, heatmap_red=heatmap_red, goals=goals)

    # Write output
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        f.write(html)

    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
