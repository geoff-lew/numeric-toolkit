#!/usr/bin/env python3
"""
identify_candidates.py — Identifies accrual candidates from a vendor spend matrix.

Usage:
    python3 identify_candidates.py <spend_matrix_json> <output_json> \
        --open-period YYYY-MM \
        [--exclusions "Vendor A,Vendor B"]

Input:  vendor_spend_matrix.json from parse_txn_lines.py
Output: JSON file with candidates and observations, plus a markdown table printed to stdout
        that the model can paste directly into the conversation.

Output JSON structure:
    {
        "candidates": [
            {
                "vendor": "...",
                "trigger": "...",
                "method": "6-mo avg",
                "proposed_amount": 1234.56,
                "flags": ["..."],
                "history": {"YYYY-MM": amount, ...}
            }
        ],
        "observations": [...],
        "markdown_table": "| # | Vendor | ... |\\n..."
    }
"""

import json
import argparse


def _month_label(ym: str) -> str:
    """Convert YYYY-MM to short label like Sep-24."""
    month_names = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
    }
    parts = ym.split("-")
    return f"{month_names.get(parts[1], parts[1])}-{parts[0][2:]}"


def _fmt(val: float) -> str:
    """Format dollar amount for table display. $0 shown as dash."""
    if val == 0:
        return "—"
    if val >= 1000:
        return f"${val:,.0f}"
    return f"${val:,.2f}"


def identify_candidates(vendors: dict, months: list, open_period: str, exclusions: set | None = None) -> tuple[list, list]:
    """
    Apply default triggers to identify accrual candidates and Section B observations.
    Returns (candidates, observations).
    """
    completed_months = [m for m in months if m < open_period]
    if not completed_months:
        return [], []

    last_completed = completed_months[-1]
    prior_5 = completed_months[:-1][-5:] if len(completed_months) > 1 else []
    exclusions = exclusions or set()

    candidates = []
    observations = []

    for vendor, spend in vendors.items():
        if vendor in exclusions:
            continue

        open_spend = spend.get(open_period, 0)
        last_spend = spend.get(last_completed, 0)

        non_zero_months = [(m, spend.get(m, 0)) for m in completed_months if spend.get(m, 0) != 0]
        non_zero_values = [v for _, v in non_zero_months]

        trigger = None
        flags = []

        # Trigger 1: $0 in open period AND >$0 in last completed month
        if open_spend == 0 and last_spend > 0:
            trigger = f"$0 in {_month_label(open_period)}, ${last_spend:,.0f} in {_month_label(last_completed)}"

        # Trigger 2: $0 in both open and last completed, but >$0 in >=3 of prior 5
        if open_spend == 0 and last_spend == 0 and prior_5:
            prior_nonzero = sum(1 for m in prior_5 if spend.get(m, 0) > 0)
            if prior_nonzero >= 3:
                trigger = f"$0 in {_month_label(open_period)} and {_month_label(last_completed)}, active {prior_nonzero}/{len(prior_5)} prior months"
                flags.append("May be cancelled or missing invoice")

        # Section B: not triggered but historically active
        if trigger is None and open_spend == 0 and last_spend == 0:
            prior_4 = completed_months[:-1][-4:] if len(completed_months) > 1 else []
            prior_4_nonzero = sum(1 for m in prior_4 if spend.get(m, 0) > 0)
            if prior_4_nonzero >= 2:
                observations.append({
                    "vendor": vendor,
                    "history": {m: spend.get(m, 0) for m in completed_months},
                    "note": f"$0 in {_month_label(open_period)} and {_month_label(last_completed)}, had spend in {prior_4_nonzero}/{len(prior_4)} prior months",
                })

        if trigger is None:
            continue

        # Estimation method
        method = ""
        proposed_amount = 0

        if len(non_zero_values) >= 6:
            recent_6 = [spend.get(m, 0) for m in completed_months[-6:]]
            proposed_amount = sum(recent_6) / 6
            method = "6-mo avg"
        elif len(non_zero_values) >= 3:
            proposed_amount = sum(non_zero_values[-3:]) / 3
            method = "3-mo avg"
        elif len(non_zero_values) >= 1:
            proposed_amount = non_zero_values[-1]
            method = "Last non-zero month"
            flags.append("Only 1-2 months of data")
        else:
            proposed_amount = 0
            method = "Estimate needed"
            flags.append("No historical data")

        candidates.append({
            "vendor": vendor,
            "open_spend": open_spend,
            "history": {m: spend.get(m, 0) for m in completed_months},
            "trigger": trigger,
            "method": method,
            "proposed_amount": round(proposed_amount, 2),
            "flags": flags,
        })

    candidates.sort(key=lambda x: x["proposed_amount"], reverse=True)
    return candidates, observations


def build_markdown_table(candidates: list, observations: list, completed_months: list) -> str:
    """Build a markdown table for direct display in chat."""
    if not candidates and not observations:
        return "No accrual candidates identified for this period."

    lines = []

    # Header row
    month_cols = " | ".join(_month_label(m) for m in completed_months)
    lines.append(f"| # | Vendor | {month_cols} | Method | Accrual | Flags |")
    lines.append(f"|---|--------|" + "|".join(["-------"] * len(completed_months)) + "|--------|---------|-------|")

    # Candidate rows
    total = 0
    for i, c in enumerate(candidates, 1):
        hist_cells = " | ".join(_fmt(c["history"].get(m, 0)) for m in completed_months)
        flag_str = "; ".join(c["flags"]) if c["flags"] else ""
        total += c["proposed_amount"]
        lines.append(f"| {i} | {c['vendor']} | {hist_cells} | {c['method']} | ${c['proposed_amount']:,.0f} | {flag_str} |")

    # Total row
    lines.append(f"| | **Total** | " + " | ".join([""] * len(completed_months)) + f" | | **${total:,.0f}** | |")

    table = "\n".join(lines)

    # Observations section
    if observations:
        table += "\n\n**Also worth reviewing** (spend went to zero, not triggered):\n"
        for o in observations:
            recent = " / ".join(f"{_month_label(m)}: {_fmt(o['history'].get(m, 0))}" for m in completed_months[-4:])
            table += f"\n- {o['vendor']}: {recent} — {o['note']}"

    return table


def main():
    parser = argparse.ArgumentParser(description="Identify accrual candidates from vendor spend matrix")
    parser.add_argument("spend_matrix", help="Path to vendor_spend_matrix.json")
    parser.add_argument("output_json", help="Path for output candidates JSON")
    parser.add_argument("--open-period", required=True, help="Open period YYYY-MM")
    parser.add_argument("--exclusions", help="Comma-separated vendor names to exclude", default="")
    args = parser.parse_args()

    with open(args.spend_matrix) as f:
        data = json.load(f)

    exclusion_set = {v.strip() for v in args.exclusions.split(",") if v.strip()} if args.exclusions else set()

    candidates, observations = identify_candidates(
        data["vendors"], data["months"], args.open_period, exclusion_set
    )

    completed_months = [m for m in data["months"] if m < args.open_period]
    md_table = build_markdown_table(candidates, observations, completed_months)

    output = {
        "candidates": candidates,
        "observations": observations,
        "markdown_table": md_table,
    }

    with open(args.output_json, "w") as f:
        json.dump(output, f, indent=2)

    # Print the table to stdout so the model can paste it into chat
    print(md_table)


if __name__ == "__main__":
    main()
