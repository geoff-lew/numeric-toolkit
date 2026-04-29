#!/usr/bin/env python3
"""
merge_flux.py — merge per-entity / per-report / per-period flux JSONs into a
single unified table.

Each input JSON is expected to be a list of:
    {
        "account_group": str,
        "account": str (optional),
        "entity": str (optional),
        "report": str (optional),
        "period": str,
        "variance_amount": float,
        "variance_pct": float,
        "commentary": str (optional),
    }

Output: a list of rows with one row per (account_group, account) pair, with
columns per (entity, report, period) keyed dimension. Sorted by total absolute
variance desc.

Usage:
    python merge_flux.py <input1.json> [<input2.json> ...] <output.json>
        [--key entity|report|period] [--materiality 10000]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("inputs", nargs="+", help="Input JSON files (last arg is output)")
    p.add_argument("--key", choices=["entity", "report", "period"], default="entity",
                   help="Which dimension becomes the column header")
    p.add_argument("--materiality", type=float, default=10000,
                   help="Minimum absolute variance to retain a row")
    args = p.parse_args()

    if len(args.inputs) < 2:
        print("ERROR: need at least one input and one output path", file=sys.stderr)
        sys.exit(2)
    *in_paths, out_path = args.inputs

    rows = defaultdict(lambda: {"variances": {}, "commentary": {}, "total": 0.0})
    seen_keys = set()

    for path_str in in_paths:
        path = Path(path_str)
        if not path.exists():
            print(f"WARN: skipping missing input {path}", file=sys.stderr)
            continue
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"WARN: bad JSON in {path}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, list):
            print(f"WARN: expected list in {path}, got {type(data).__name__}", file=sys.stderr)
            continue
        for entry in data:
            group = entry.get("account_group") or entry.get("group") or "(unknown)"
            account = entry.get("account") or ""
            row_key = (group, account)
            col_key = entry.get(args.key) or path.stem
            seen_keys.add(col_key)
            amount = float(entry.get("variance_amount") or 0)
            pct = entry.get("variance_pct")
            commentary = entry.get("commentary") or ""
            rows[row_key]["variances"][col_key] = {
                "amount": amount,
                "pct": pct,
            }
            if commentary:
                rows[row_key]["commentary"][col_key] = commentary
            rows[row_key]["total"] += abs(amount)

    output = []
    for (group, account), payload in rows.items():
        if payload["total"] < args.materiality:
            continue
        flat = {
            "account_group": group,
            "account": account,
            "total_abs_variance": round(payload["total"], 2),
        }
        for k in sorted(seen_keys):
            v = payload["variances"].get(k, {})
            flat[f"{k}__amount"] = v.get("amount")
            flat[f"{k}__pct"] = v.get("pct")
            if k in payload["commentary"]:
                flat[f"{k}__commentary"] = payload["commentary"][k]
        output.append(flat)

    output.sort(key=lambda r: r["total_abs_variance"], reverse=True)
    Path(out_path).write_text(json.dumps(output, indent=2))
    print(f"Merged {len(in_paths)} inputs → {len(output)} rows (materiality ≥ {args.materiality}) → {out_path}")


if __name__ == "__main__":
    main()
