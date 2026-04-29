#!/usr/bin/env python3
"""
collapse_to_groups.py — collapse an IS or BS report into executive groups.

Input:  IS/BS report TSV plus a chart-of-accounts JSON (from list_financial_accounts).
Output: JSON with one row per executive group, with current and prior period totals.

The chart-of-accounts JSON is expected to be a list of:
    {"external_id": "...", "name": "...", "category": "REVENUE|EXPENSE|ASSET|LIABILITY|EQUITY",
     "code": "...", "parent_path": "..."}

The mapping from chart category → executive group is configurable via --mapping
(JSON file). Defaults are baked in for IS and BS.

Usage:
    python collapse_to_groups.py --report report.tsv --coa coa.json --statement is
        --out exec_is.json [--mapping custom_map.json]
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


DEFAULT_IS_MAPPING = {
    # Group → list of (category, name_pattern) tuples
    "Revenue": [("REVENUE", r".*")],
    "Cost of Revenue": [("EXPENSE", r"cost of (goods|revenue|sales)|cogs|hosting|merchant fee")],
    "R&D": [("EXPENSE", r"r\s*&\s*d|research|engineering|product development")],
    "Sales & Marketing": [("EXPENSE", r"sales|marketing|advertising|brand|customer acquisition")],
    "General & Administrative": [("EXPENSE", r"general|admin|corporate|finance|legal|hr|human resources")],
    "Other Income / (Expense)": [("EXPENSE", r"interest|fx|foreign exchange|other (income|expense)"),
                                 ("REVENUE", r"interest|other income")],
    "Income Tax": [("EXPENSE", r"tax|provision")],
}

DEFAULT_BS_MAPPING = {
    "Cash & Equivalents": [("ASSET", r"cash|short.?term invest")],
    "Accounts Receivable": [("ASSET", r"receivab|unbilled")],
    "Other Current Assets": [("ASSET", r"prepaid|inventory|deposit")],
    "Fixed Assets, net": [("ASSET", r"pp&e|property|equipment|fixed asset|accumulated depr")],
    "Intangibles & Other": [("ASSET", r"intangib|goodwill|capitalized")],
    "Accounts Payable": [("LIABILITY", r"payable|trade payab")],
    "Accrued Liabilities": [("LIABILITY", r"accrued")],
    "Deferred Revenue": [("LIABILITY", r"deferred (revenue|income)")],
    "Long-term Debt": [("LIABILITY", r"loan|note|debt|borrowing")],
    "Other Current Liabilities": [("LIABILITY", r".*")],
    "Total Equity": [("EQUITY", r".*")],
}


def to_float(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s in {"-", "—", "–"}:
        return 0.0
    s = re.sub(r"[$£€¥,\s]", "", s)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def detect_period_columns(headers):
    out = []
    for i, h in enumerate(headers):
        if re.search(r"(19|20)\d{2}", h) or re.match(r"^\d{4}-\d{2}", h.strip()):
            out.append((i, h))
    return out


def assign_group(category, name, mapping):
    """Walk the mapping in order and return the first matching group."""
    for group, patterns in mapping.items():
        for cat, pattern in patterns:
            if cat and category and cat.upper() != category.upper():
                continue
            if re.search(pattern, name or "", re.IGNORECASE):
                return group
    return None


def extract_account_external_id(account_path):
    """Pull the deepest leaf account's external_id from a Numeric Account path.

    Real Numeric reports encode the row key in the Account column as a path:
        path#GRP > path_s#GRP/SECTION_ID > path#GRP/ACCOUNT_ID
    The deepest segment's id-after-the-last-slash is the account external_id.
    Group rows (single segment) and subtotal rows (path_s) return None.
    """
    if not account_path:
        return None
    s = str(account_path).strip()
    if not s or s.startswith("metric_row#") or s.startswith("computed_row#"):
        return None
    segments = [p.strip() for p in s.split(">") if "#" in p]
    if not segments:
        return None
    last = segments[-1]
    prefix, _, ident = last.partition("#")
    prefix = prefix.strip()
    if prefix != "path" or "/" not in ident:
        return None
    return ident.rsplit("/", 1)[-1].strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--report", required=True)
    p.add_argument("--coa", required=True, help="Chart of accounts JSON")
    p.add_argument("--statement", choices=["is", "bs"], required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--mapping", help="Custom mapping JSON")
    p.add_argument("--report-config", help="Path to the report config JSON from list_reports — "
                   "used to detect non-account-pivoted reports and prevent silent wrong totals")
    p.add_argument("--allow-non-account-pivot", action="store_true",
                   help="Override the safety check and run anyway. Use only when the user has "
                   "confirmed the leaf pivot is acceptable for executive-group rollup.")
    args = p.parse_args()

    # Safety check: refuse to run on reports whose deepest pivot is not account.external_id.
    # On those, leaf row IDs encode counterparty/customer/department — looking them up in the
    # COA produces silent wrong totals. See severity-1 issue in toolkit changelog.
    if args.report_config:
        try:
            cfg_raw = json.loads(Path(args.report_config).read_text())
            cfg = cfg_raw[0] if isinstance(cfg_raw, list) and cfg_raw else cfg_raw
            rc = cfg.get("reportConfig", cfg)
            pivots = rc.get("pivots", []) or []
            visible = [p for p in pivots if not p.get("hidden", False)]
            if visible:
                rightmost = visible[-1]
                pivot_type = rightmost.get("type", "")
                if pivot_type != "account.external_id":
                    if not args.allow_non_account_pivot:
                        print(
                            f"ERROR: report has a non-account leaf pivot "
                            f"(rightmost visible pivot: {pivot_type}). Running collapse_to_groups "
                            f"on this report would silently produce wrong totals because leaf "
                            f"row IDs are not account external_ids. Either:\n"
                            f"  1. Use a different saved report whose leaf pivot is account.external_id.\n"
                            f"  2. Use the report's own filterGroups for grouping (skip this script).\n"
                            f"  3. Pass --allow-non-account-pivot if the leaf pivot's IDs are "
                            f"semantically interchangeable with account external_ids in the COA "
                            f"(rare; user must confirm).",
                            file=sys.stderr,
                        )
                        sys.exit(3)
                    print(f"WARNING: running on non-account leaf pivot ({pivot_type}). "
                          f"Output may be wrong.", file=sys.stderr)
        except (json.JSONDecodeError, OSError, KeyError) as e:
            print(f"WARNING: could not parse --report-config ({e}); proceeding without "
                  f"pivot-shape safety check.", file=sys.stderr)

    if args.mapping:
        mapping = json.loads(Path(args.mapping).read_text())
    else:
        mapping = DEFAULT_IS_MAPPING if args.statement == "is" else DEFAULT_BS_MAPPING

    coa_raw = json.loads(Path(args.coa).read_text())
    # list_financial_accounts returns {"accounts": [...]}; accept either shape.
    coa = coa_raw["accounts"] if isinstance(coa_raw, dict) and "accounts" in coa_raw else coa_raw
    coa_by_id = {a.get("external_id"): a for a in coa if a.get("external_id")}

    rep_path = Path(args.report)
    with rep_path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        headers = next(reader, None) or []
        cols = {h.lower().strip(): i for i, h in enumerate(headers)}
        # Numeric reports have separate Account (path) and Name (label) columns.
        account_idx = cols.get("account")
        name_idx = cols.get("name")
        if account_idx is None:
            print("ERROR: no 'Account' column in report header", file=sys.stderr)
            sys.exit(2)
        if name_idx is None:
            name_idx = account_idx + 1 if account_idx + 1 < len(headers) else account_idx
        period_cols = detect_period_columns(headers)
        if not period_cols:
            print("ERROR: no period columns detected", file=sys.stderr)
            sys.exit(2)

        groups = defaultdict(lambda: {label: 0.0 for _, label in period_cols})
        unmapped = []
        for row in reader:
            if not row or not any(c.strip() for c in row):
                continue
            account_path = row[account_idx].strip() if account_idx < len(row) else ""
            name = row[name_idx].strip() if name_idx < len(row) else ""
            external_id = extract_account_external_id(account_path)
            # Skip non-leaf rows (groups, subtotals, metrics, computed totals) —
            # they don't represent additive account balances we should re-sum.
            if not external_id:
                continue
            coa_entry = coa_by_id.get(external_id)
            category = coa_entry.get("category") if coa_entry else None
            coa_name = coa_entry.get("name") if coa_entry else name
            group = assign_group(category, coa_name, mapping)
            if not group:
                # Fall back to the report's display name
                group = assign_group(category, name, mapping)
            if not group:
                unmapped.append({"name": name, "category": category, "external_id": external_id})
                continue
            for idx, label in period_cols:
                if idx < len(row):
                    v = to_float(row[idx])
                    if v is not None:
                        groups[group][label] += v

    output = {
        "statement": args.statement,
        "period_columns": [label for _, label in period_cols],
        "groups": [{"group_name": g, "values": dict(v)} for g, v in groups.items()],
        "unmapped": unmapped,
    }
    Path(args.out).write_text(json.dumps(output, indent=2))
    print(f"Collapsed report into {len(groups)} groups ({len(unmapped)} unmapped) → {args.out}")


if __name__ == "__main__":
    main()
