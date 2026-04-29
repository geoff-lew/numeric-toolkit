#!/usr/bin/env python3
"""
aggregate_anomalies.py — flag GL × department anomalies from a department-pivoted
Numeric report.

Numeric department-pivoted reports use the same TSV shape as a regular IS:
    Account                                        Name              ... period columns
    path#GRP_DEPT                                  G&A - OPEX
    path#GRP_DEPT > path_s#... > path#.../{ACCT}   {acct_code} - {name}
    ...

The Account column path encodes the department in its top-level segment id;
that segment's group-header row carries the human-readable department name
(e.g., "G&A - OPEX", "R&D - OPEX", "Cost of Revenue").

For each leaf account row, the parent group is the department. Pattern rules
flag (account_code, anomalous_department) combinations and structural rules
catch new-large items and extreme variances.

Rule JSON shape:
    [
        {
            "id": "RULE_NAME",
            "account_pattern": "^80\\d{4}",        // regex on account code
            "anomaly_dept_pattern": "S&M|G&A|COGS",
            "min_amount": 5000
        },
        ...
    ]

Usage:
    python aggregate_anomalies.py <report.tsv> <rules.json> <output.json>
        [--min-amount 5000] [--new-large-threshold 10000]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path


def to_float(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in {"-", "—", "–"}:
        return 0.0
    s = re.sub(r"[$£€¥,\s]", "", s)
    s = s.replace("%", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def detect_period_columns(headers):
    skip = {"account", "name", "priority", "variance ($)", "variance (%)",
            "has activity", "threshold state"}
    out = []
    for i, h in enumerate(headers):
        if not h:
            continue
        if h.strip().lower() in skip:
            continue
        if re.search(r"(19|20)\d{2}", h) or re.match(r"^\d{4}-\d{2}", h.strip()):
            out.append((i, h))
    return out


def parse_path(account_path):
    """Parse a Numeric Account path into segments. Returns (row_kind, segments, leaf_external_id)."""
    if not account_path:
        return None, [], None
    s = str(account_path).strip()
    if not s:
        return None, [], None
    if s.startswith("metric_row#") or s.startswith("computed_row#"):
        return "metric", [], None
    segments = []
    for part in s.split(">"):
        part = part.strip()
        if "#" not in part:
            continue
        prefix, _, ident = part.partition("#")
        segments.append({"prefix": prefix.strip(), "id": ident.strip()})
    if not segments:
        return "other", [], None
    last = segments[-1]
    if len(segments) == 1 and last["prefix"] == "path":
        return "group", segments, None
    if last["prefix"] == "path_s":
        return "subtotal", segments, None
    if last["prefix"] == "path" and "/" in last["id"]:
        return "leaf", segments, last["id"].rsplit("/", 1)[-1]
    return "other", segments, None


def extract_account_code(name):
    m = re.match(r"^\s*(\d{4,6})\b", name or "")
    return m.group(1) if m else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("report", help="Department-pivoted report TSV")
    p.add_argument("rules", help="Rules JSON file")
    p.add_argument("output", help="Output JSON file")
    p.add_argument("--min-amount", type=float, default=5000,
                   help="Default materiality threshold")
    p.add_argument("--new-large-threshold", type=float, default=10000,
                   help="Threshold for 'new large item' (prior=$0, current>X)")
    args = p.parse_args()

    rules = json.loads(Path(args.rules).read_text())
    rep_path = Path(args.report)
    if not rep_path.exists():
        print(f"ERROR: report not found: {rep_path}", file=sys.stderr)
        sys.exit(2)

    # Pass 1: collect group-header labels (top-level path id -> dept name)
    rows = []
    group_labels = {}
    with rep_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        headers = next(reader, None) or []
        cols = {h.lower().strip(): i for i, h in enumerate(headers)}
        account_idx = cols.get("account")
        name_idx = cols.get("name")
        period_cols = detect_period_columns(headers)
        if account_idx is None or not period_cols:
            print("ERROR: report missing Account column or period columns", file=sys.stderr)
            sys.exit(2)
        if name_idx is None:
            name_idx = account_idx + 1

        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            account_path = row[account_idx].strip() if account_idx < len(row) else ""
            name = row[name_idx].strip() if name_idx < len(row) else ""
            row_kind, segments, leaf_id = parse_path(account_path)
            if row_kind == "group" and segments:
                group_labels[segments[0]["id"]] = name
            balances = {}
            for idx, label in period_cols:
                if idx < len(row):
                    balances[label] = to_float(row[idx])
            rows.append((row_kind, segments, leaf_id, name, balances))

    if len(period_cols) >= 2:
        current_label = period_cols[-1][1]
        prior_label = period_cols[-2][1]
    else:
        current_label = period_cols[-1][1]
        prior_label = None

    anomalies = []
    seen = set()  # (code, dept) keys to avoid duplicates across rule matches

    for row_kind, segments, leaf_id, name, balances in rows:
        if row_kind != "leaf" or not segments:
            continue
        department = group_labels.get(segments[0]["id"]) or "(unknown)"
        code = extract_account_code(name)
        current = balances.get(current_label)
        prior = balances.get(prior_label) if prior_label else None
        if current is None:
            continue

        # Pattern rules
        for rule in rules:
            acct_pat = rule.get("account_pattern")
            anom_dept_pat = rule.get("anomaly_dept_pattern")
            if not acct_pat or not anom_dept_pat:
                continue
            account_match = (code and re.match(acct_pat, code)) or re.search(acct_pat, name)
            if not account_match:
                continue
            if not re.search(anom_dept_pat, department, re.IGNORECASE):
                continue
            threshold = rule.get("min_amount", args.min_amount)
            if abs(current) < threshold:
                continue
            key = (code or name, department, rule.get("id", "PATTERN"))
            if key in seen:
                continue
            seen.add(key)
            anomalies.append({
                "account": name,
                "account_code": code,
                "department": department,
                "amount": current,
                "prior_amount": prior,
                "rule_triggered": rule.get("id", "PATTERN"),
                "period": current_label,
            })

        # Structural: new large item (prior=0, current > threshold)
        if prior is not None and prior == 0 and current > args.new_large_threshold:
            key = (code or name, department, "NEW_LARGE")
            if key not in seen:
                seen.add(key)
                anomalies.append({
                    "account": name,
                    "account_code": code,
                    "department": department,
                    "amount": current,
                    "prior_amount": prior,
                    "rule_triggered": "NEW_LARGE",
                    "period": current_label,
                })

        # Structural: extreme variance (>500%, both non-zero)
        if prior is not None and prior != 0 and current != 0:
            pct = (current - prior) / abs(prior) * 100
            if abs(pct) > 500 and abs(current) >= args.min_amount:
                key = (code or name, department, "EXTREME_VARIANCE")
                if key not in seen:
                    seen.add(key)
                    anomalies.append({
                        "account": name,
                        "account_code": code,
                        "department": department,
                        "amount": current,
                        "prior_amount": prior,
                        "rule_triggered": "EXTREME_VARIANCE",
                        "pct_change": round(pct, 1),
                        "period": current_label,
                    })

    Path(args.output).write_text(json.dumps(anomalies, indent=2))
    print(f"Wrote {len(anomalies)} anomalies to {args.output}")


if __name__ == "__main__":
    main()
