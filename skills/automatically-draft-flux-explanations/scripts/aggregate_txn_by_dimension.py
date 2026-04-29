#!/usr/bin/env python3
"""
aggregate_txn_by_dimension.py — group 6 months of transaction lines into
rollups by vendor, customer, department, class, and posting month.

Input:  transaction-lines TSV (from query_transaction_lines).
Output: JSON with monthly totals and per-dimension subtotals, oriented around
        the variance the flux explanation needs to cover.

Usage:
    python aggregate_txn_by_dimension.py <txn.tsv> <output.json>
        [--amount-col normal_amount] [--top-n 20]
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


def to_float(s):
    if s is None:
        return 0.0
    s = str(s).strip()
    if not s:
        return 0.0
    s = re.sub(r"[$£€¥,\s]", "", s)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def month_of(date_str):
    """Extract YYYY-MM from a date string. Handles ISO and MM/DD/YYYY."""
    if not date_str:
        return None
    s = date_str.strip()
    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input", help="Transaction lines TSV")
    p.add_argument("output", help="Output JSON")
    p.add_argument("--amount-col", default="normal_amount",
                   help="Amount column to aggregate (default normal_amount; falls back to net_amount)")
    p.add_argument("--top-n", type=int, default=20,
                   help="Top N entries to keep per dimension (rest grouped as 'Other')")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        sys.exit(2)

    monthly_totals = defaultdict(float)
    by_dim = {
        "by_vendor": defaultdict(lambda: defaultdict(float)),
        "by_customer": defaultdict(lambda: defaultdict(float)),
        "by_department": defaultdict(lambda: defaultdict(float)),
        "by_class": defaultdict(lambda: defaultdict(float)),
    }
    total_rows = 0

    with in_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames:
            print("ERROR: empty TSV", file=sys.stderr)
            sys.exit(2)
        amt_col = args.amount_col if args.amount_col in reader.fieldnames else None
        if amt_col is None:
            amt_col = "net_amount" if "net_amount" in reader.fieldnames else None
        if amt_col is None:
            print(f"ERROR: no amount column found (tried {args.amount_col}, net_amount)", file=sys.stderr)
            sys.exit(2)

        # Identify dimension columns case-insensitively
        cols_lower = {c.lower(): c for c in reader.fieldnames}
        date_col = cols_lower.get("posting_date") or cols_lower.get("transaction_date") or cols_lower.get("date")
        vendor_col = cols_lower.get("vendor") or cols_lower.get("counterparty")
        customer_col = cols_lower.get("customer")
        dept_col = cols_lower.get("department")
        class_col = cols_lower.get("class")

        for row in reader:
            total_rows += 1
            amt = to_float(row.get(amt_col))
            if amt == 0:
                continue
            month = month_of(row.get(date_col, "")) if date_col else None
            if month:
                monthly_totals[month] += amt
            for key, col in (("by_vendor", vendor_col),
                             ("by_customer", customer_col),
                             ("by_department", dept_col),
                             ("by_class", class_col)):
                if col and row.get(col):
                    val = row[col].strip()
                    if val:
                        by_dim[key][val][month or "unknown"] += amt
                        by_dim[key][val]["__total__"] += amt

    # Sort, take top-N, aggregate the rest into "Other"
    def top_n(d, n):
        items = sorted(d.items(), key=lambda kv: abs(kv[1].get("__total__", 0)), reverse=True)
        top = items[:n]
        rest = items[n:]
        out = {k: dict(v) for k, v in top}
        if rest:
            other = defaultdict(float)
            for _, v in rest:
                for mk, mv in v.items():
                    other[mk] += mv
            out["__other__"] = dict(other)
        return out

    output = {
        "monthly_totals": dict(sorted(monthly_totals.items())),
        "row_count": total_rows,
        "amount_column": amt_col,
    }
    for k, v in by_dim.items():
        if v:
            output[k] = top_n(v, args.top_n)

    Path(args.output).write_text(json.dumps(output, indent=2, default=float))
    print(f"Aggregated {total_rows} rows across {len(monthly_totals)} months → {args.output}")


if __name__ == "__main__":
    main()
