#!/usr/bin/env python3
"""
parse_report.py — turn a Numeric report TSV into a JSON list of drillable rows.

Numeric report TSVs have this shape:
    Account                                        Name              ... period columns
    path#GRP                                       Revenue                 ...
    path#GRP > path_s#GRP/54                       4000 - License Rev      ...
    path#GRP > path_s#GRP/54 > path#GRP/452        4005 - License Rev ...  ...
    metric_row#mtr_xxx                             Gross Profit            ...

The Account column holds a path. Rows are classified by path shape:
    - Group header (1 segment, starts with "path#"): use Name as the group label.
    - Subtotal (2 segments, ends in "path_s#..."): not drillable.
    - Leaf account (3+ segments OR ends in "path#GRP/<n>"): drillable.
    - Metric/computed (starts with "metric_row#" / "computed_row#"): not drillable.

For drillable rows, the row key for query_transaction_lines is the rightmost
segment's ID portion (after the `#`), with type "path".

Usage:
    python parse_report.py <input.tsv> <output.json> [--include-non-drillable]
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


def parse_account_path(account):
    """
    Parse the Numeric Account column into segments. Returns:
        {
            "raw": original string,
            "segments": [{prefix, id} for each segment],
            "row_kind": "group" | "subtotal" | "leaf" | "metric" | "computed" | "other",
            "key": {"id": ..., "type": "path"} or None,
        }
    """
    if not account:
        return None
    s = str(account).strip()
    if not s:
        return None

    # Metric / computed rows are easy
    if s.startswith("metric_row#"):
        return {"raw": s, "segments": [], "row_kind": "metric", "key": None}
    if s.startswith("computed_row#") or s.startswith("custom_group#"):
        return {"raw": s, "segments": [], "row_kind": "computed", "key": None}

    segments = []
    for part in s.split(">"):
        part = part.strip()
        if "#" not in part:
            continue
        prefix, ident = part.split("#", 1)
        segments.append({"prefix": prefix.strip(), "id": ident.strip()})

    if not segments:
        return {"raw": s, "segments": [], "row_kind": "other", "key": None}

    last = segments[-1]
    last_prefix = last["prefix"]
    last_id = last["id"]

    # Group header: 1 segment starting with "path"
    if len(segments) == 1 and last_prefix == "path":
        return {"raw": s, "segments": segments, "row_kind": "group", "key": None}

    # Subtotal: rightmost prefix is "path_s"
    if last_prefix == "path_s":
        return {"raw": s, "segments": segments, "row_kind": "subtotal", "key": None}

    # Leaf account: ends in path# with a numeric suffix in the id
    if last_prefix == "path":
        # The transaction-lines key is the id portion of the deepest segment.
        return {
            "raw": s,
            "segments": segments,
            "row_kind": "leaf",
            "key": {"id": last_id, "type": "path"},
        }

    return {"raw": s, "segments": segments, "row_kind": "other", "key": None}


def detect_period_columns(headers):
    """Detect period columns. Numeric uses labels like 'Q4 2024', '2024-12', 'Dec 2024'."""
    skip = {"account", "name", "priority", "variance ($)", "variance (%)",
            "has activity", "threshold state", "group", "key", "type"}
    out = []
    for i, h in enumerate(headers):
        if not h:
            continue
        hl = h.strip().lower()
        if hl in skip:
            continue
        # Heuristic: contains a 4-digit year, OR matches MMM YYYY / YYYY-MM
        if re.search(r"(19|20)\d{2}", h) or re.match(r"^\d{4}-\d{2}", h.strip()):
            out.append((i, h))
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="Path to report TSV")
    p.add_argument("output", help="Path to output JSON")
    p.add_argument("--include-non-drillable", action="store_true",
                   help="Keep group/subtotal/metric rows in the output")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    # Numeric reports list leaf rows first and the group header row last within
    # each section. Walk the file once, collecting all rows, then look up each
    # leaf's group label from the group header sharing its top-level path id.
    raw_rows = []
    group_labels = {}  # group_id (segment 0 id) -> human-readable group name
    with in_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        headers = next(reader, None)
        if not headers:
            print("ERROR: empty TSV", file=sys.stderr)
            sys.exit(2)
        cols = {h.strip().lower(): i for i, h in enumerate(headers)}
        account_idx = cols.get("account")
        name_idx = cols.get("name", 1 if account_idx == 0 else 0)
        period_cols = detect_period_columns(headers)

        if account_idx is None:
            print("ERROR: no 'Account' column in TSV header", file=sys.stderr)
            sys.exit(2)

        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            account = row[account_idx].strip() if account_idx < len(row) else ""
            name = row[name_idx].strip() if name_idx is not None and name_idx < len(row) else ""
            parsed = parse_account_path(account)
            if not parsed:
                continue
            if parsed["row_kind"] == "group" and parsed["segments"]:
                group_labels[parsed["segments"][0]["id"]] = name
            balances = {}
            for idx, label in period_cols:
                if idx < len(row):
                    balances[label] = to_float(row[idx])
            raw_rows.append((parsed, name, balances))

    rows_out = []
    for parsed, name, balances in raw_rows:
        if parsed["row_kind"] != "leaf" and not args.include_non_drillable:
            continue
        group_name = None
        if parsed["segments"]:
            group_name = group_labels.get(parsed["segments"][0]["id"])
        primary_balance = next(reversed(balances.values())) if balances else None
        rows_out.append({
            "account_name": name,
            "key": parsed["key"],
            "type": parsed["row_kind"],
            "group": group_name,
            "balance": primary_balance,
            "period_balances": balances,
        })

    Path(args.output).write_text(json.dumps(rows_out, indent=2))
    drillable = sum(1 for r in rows_out if r["type"] == "leaf")
    print(f"Wrote {len(rows_out)} rows ({drillable} drillable) to {args.output}")


if __name__ == "__main__":
    main()
