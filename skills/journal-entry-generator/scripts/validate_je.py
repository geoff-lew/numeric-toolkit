#!/usr/bin/env python3
"""Validate journal entry data before NetSuite import.

Implements the 14 validation rules from references/validation-rules.md.
Reads JE data as JSON, runs checks, outputs pass/fail with details.

Usage:
    python validate_je.py je_data.json
    python validate_je.py je_data.json --json

Input JSON format:
{
  "je_type": 1,
  "entries": [
    {
      "external_id": "JE-ACM-202602-VENDOR-001",
      "date": "2026-02-28",
      "subsidiary": "10 Acme Corp US",
      "currency": "USD",
      "exchange_rate": 1.0,
      "memo": "EOR Vendor Feb 2026 Invoice",
      "lines": [
        {
          "account": "6122 Payroll Expense : Salaries",
          "debit": 149345.38,
          "credit": null,
          "department": "500 S&M : 520 Sales",
          "memo": "Salaries — 45 employees"
        }
      ]
    }
  ],
  "source_total": 355864.00,
  "tie_out_mode": "total_debit",
  "form_required_fields": ["department", "location"]
}
"""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path


class ValidationResult:
    def __init__(self):
        self.checks = []
        self.errors = []
        self.warnings = []

    def passed(self, rule_num: int, description: str):
        self.checks.append({"rule": rule_num, "status": "PASS", "description": description})

    def failed(self, rule_num: int, description: str, detail: str):
        self.checks.append({"rule": rule_num, "status": "FAIL", "description": description, "detail": detail})
        self.errors.append(f"Rule {rule_num}: {description} — {detail}")

    def warned(self, rule_num: int, description: str, detail: str):
        self.checks.append({"rule": rule_num, "status": "WARN", "description": description, "detail": detail})
        self.warnings.append(f"Rule {rule_num}: {description} — {detail}")

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> dict:
        return {
            "valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": self.checks,
        }


def to_decimal(value) -> Decimal:
    if value is None or value == "" or value == 0:
        return Decimal("0")
    return Decimal(str(value))


def validate_entry(entry: dict, data: dict) -> ValidationResult:
    """Validate a single journal entry (rules 1, 3-12)."""
    result = ValidationResult()
    lines = entry.get("lines", [])

    if not lines:
        result.failed(1, "DR = CR", "Entry has no lines")
        return result

    # Rule 1: DR = CR
    total_dr = sum(to_decimal(l.get("debit")) for l in lines)
    total_cr = sum(to_decimal(l.get("credit")) for l in lines)
    diff = total_dr - total_cr

    if diff == 0:
        result.passed(1, "DR = CR")
    else:
        result.failed(1, "DR = CR", f"DR={total_dr}, CR={total_cr}, diff={diff}")

    # Rule 3: FX consistency
    rates = set()
    for line in lines:
        rate = line.get("exchange_rate", entry.get("exchange_rate"))
        if rate is not None:
            rates.add(str(rate))
    if len(rates) <= 1:
        result.passed(3, "FX consistency")
    else:
        result.failed(3, "FX consistency", f"Multiple exchange rates found: {rates}")

    # Rule 4: Rounding
    if abs(diff) > Decimal("0.01") and diff != 0:
        result.warned(4, "Rounding", f"DR-CR diff of {diff} exceeds penny tolerance")
    else:
        result.passed(4, "Rounding")

    # Rule 5: Account populated
    missing_accounts = [i for i, l in enumerate(lines) if not l.get("account")]
    if not missing_accounts:
        result.passed(5, "Account populated")
    else:
        result.failed(5, "Account populated", f"Lines missing account: {missing_accounts}")

    # Rule 6: Form-required fields (from input JSON top level)
    required_fields = data.get("form_required_fields", [])
    for field in required_fields:
        field_lower = field.lower()
        missing = [i for i, l in enumerate(lines) if not l.get(field_lower)]
        if not missing:
            result.passed(6, f"Form-required: {field}")
        else:
            result.failed(6, f"Form-required: {field}", f"Missing on lines: {missing}")

    # Rule 7: Single-sided lines
    double_sided = [
        i for i, l in enumerate(lines)
        if to_decimal(l.get("debit")) != 0 and to_decimal(l.get("credit")) != 0
    ]
    if not double_sided:
        result.passed(7, "Single-sided lines")
    else:
        result.failed(7, "Single-sided lines", f"Lines with both DR and CR: {double_sided}")

    # Rule 8: Date consistency
    dates = set()
    entry_date = entry.get("date")
    if entry_date:
        dates.add(entry_date)
    for line in lines:
        line_date = line.get("date")
        if line_date:
            dates.add(line_date)
    if len(dates) <= 1:
        result.passed(8, "Date consistency")
    else:
        result.failed(8, "Date consistency", f"Multiple dates found: {dates}")

    # Rule 9: Subsidiary consistency
    subsidiaries = set()
    entry_sub = entry.get("subsidiary")
    if entry_sub:
        subsidiaries.add(entry_sub)
    for line in lines:
        line_sub = line.get("subsidiary") or line.get("line_subsidiary")
        if line_sub:
            subsidiaries.add(line_sub)

    to_sub = entry.get("to_subsidiary")
    if len(subsidiaries) <= 1 and not to_sub:
        result.passed(9, "Subsidiary consistency")
    elif to_sub:
        if len(lines) >= 4:
            result.passed(9, "Subsidiary consistency (intercompany)")
        else:
            result.failed(9, "Subsidiary consistency",
                          f"Intercompany JE needs min 4 lines, has {len(lines)}")
    else:
        result.warned(9, "Subsidiary consistency",
                      f"Multiple subsidiaries without To Subsidiary: {subsidiaries}")

    # Rule 10: External ID format
    ext_id = entry.get("external_id")
    if ext_id and len(ext_id) > 0:
        result.passed(10, "External ID present")
    else:
        result.failed(10, "External ID present", "Missing External ID")

    # Rule 11: No BS items expensed (heuristic)
    bs_keywords = ["deposit", "prepaid", "security deposit", "refundable"]
    pl_prefixes = ["5", "6", "7", "8"]
    for i, line in enumerate(lines):
        memo = str(line.get("memo", "")).lower()
        acct_num = "".join(c for c in str(line.get("account", "")) if c.isdigit())[:1]
        for kw in bs_keywords:
            if kw in memo and acct_num in pl_prefixes:
                result.warned(11, "BS item possibly expensed",
                              f"Line {i}: memo contains '{kw}' but account starts with {acct_num}")

    # Rule 12: Expense direction
    expense_prefixes = ["5", "6", "7"]
    for i, line in enumerate(lines):
        acct_num = "".join(c for c in str(line.get("account", "")) if c.isdigit())[:1]
        credit = to_decimal(line.get("credit"))
        memo = str(line.get("memo", "")).lower()
        if acct_num in expense_prefixes and credit > 0:
            if "reversal" not in memo and "reverse" not in memo:
                result.warned(12, "Expense direction",
                              f"Line {i}: expense account credited without reversal in memo")

    return result


def validate_type_specific(entry: dict, je_type: int) -> ValidationResult:
    """Rules 13-14: type-specific checks."""
    result = ValidationResult()
    lines = entry.get("lines", [])

    # Rule 13: Reclass account-level net (Type 3)
    if je_type == 3:
        account_nets = {}
        for line in lines:
            acct = line.get("account", "")
            dr = to_decimal(line.get("debit"))
            cr = to_decimal(line.get("credit"))
            account_nets[acct] = account_nets.get(acct, Decimal("0")) + dr - cr

        unbalanced = {a: n for a, n in account_nets.items() if n != 0}
        if not unbalanced:
            result.passed(13, "Reclass account-level net")
        else:
            result.warned(13, "Reclass account-level net",
                          f"Accounts with non-zero net: {unbalanced}")

    # Rule 14: Entity tab balance (Type 4)
    if je_type == 4:
        sub_balances = {}
        for line in lines:
            sub = line.get("line_subsidiary", entry.get("subsidiary", "default"))
            dr = to_decimal(line.get("debit"))
            cr = to_decimal(line.get("credit"))
            sub_balances[sub] = sub_balances.get(sub, Decimal("0")) + dr - cr

        unbalanced = {s: b for s, b in sub_balances.items() if b != 0}
        if not unbalanced:
            result.passed(14, "Entity tab balance")
        else:
            result.failed(14, "Entity tab balance",
                          f"Unbalanced entities: {unbalanced}")

    return result


def validate_source_tieout(data: dict) -> ValidationResult:
    """Rule 2: JE total ties to source document total."""
    result = ValidationResult()
    source_total = data.get("source_total")
    if source_total is None:
        result.warned(2, "Source tie-out", "No source_total provided — skipped")
        return result

    source = to_decimal(source_total)
    entries = data.get("entries", [])
    mode = data.get("tie_out_mode", "total_debit")

    if mode == "total_debit":
        je_total = Decimal("0")
        for entry in entries:
            for line in entry.get("lines", []):
                je_total += to_decimal(line.get("debit"))
        label = "total DR"

    elif mode == "net":
        je_total = Decimal("0")
        for entry in entries:
            for line in entry.get("lines", []):
                je_total += to_decimal(line.get("debit")) - to_decimal(line.get("credit"))
        label = "net (DR-CR)"

    elif mode == "allocation_base":
        je_total = Decimal("0")
        for entry in entries:
            clearing_acct = entry.get("clearing_account", "2199")
            for line in entry.get("lines", []):
                acct_num = "".join(c for c in str(line.get("account", "")) if c.isdigit())
                if not acct_num.startswith(clearing_acct):
                    je_total += to_decimal(line.get("debit"))
        label = "allocation DR (excl. clearing)"

    else:
        result.warned(2, "Source tie-out", f"Unknown tie_out_mode '{mode}' — skipped")
        return result

    diff = abs(je_total - source)
    if diff <= Decimal("0.01"):
        result.passed(2, f"Source tie-out ({label})")
    else:
        result.failed(2, f"Source tie-out ({label})",
                      f"JE {label}={je_total}, source={source}, diff={diff}")

    return result


def main():
    parser = argparse.ArgumentParser(description="Validate JE data for NetSuite import")
    parser.add_argument("input", help="Path to JE data JSON file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        data = json.load(f)

    entries = data.get("entries", [])
    je_type = data.get("je_type")
    all_results = []

    for entry in entries:
        ext_id = entry.get("external_id", "unknown")
        entry_result = validate_entry(entry, data)
        all_results.append({"external_id": ext_id, "result": entry_result.to_dict()})

        if je_type in (3, 4):
            type_result = validate_type_specific(entry, je_type)
            all_results.append({"check": f"type_{je_type}_rules", "result": type_result.to_dict()})

    tieout = validate_source_tieout(data)
    all_results.append({"check": "source_tieout", "result": tieout.to_dict()})

    overall_valid = all(
        r.get("result", {}).get("valid", True) for r in all_results
    )
    total_errors = sum(
        r.get("result", {}).get("error_count", 0) for r in all_results
    )
    total_warnings = sum(
        r.get("result", {}).get("warning_count", 0) for r in all_results
    )

    output = {
        "valid": overall_valid,
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "results": all_results,
    }

    if args.json:
        print(json.dumps(output, indent=2, default=str))
    else:
        status = "PASS" if overall_valid else "FAIL"
        print(f"Validation: {status} ({total_errors} errors, {total_warnings} warnings)")
        print()
        for r in all_results:
            label = r.get("external_id") or r.get("check")
            res = r["result"]
            print(f"  {label}: {'PASS' if res['valid'] else 'FAIL'}")
            for err in res.get("errors", []):
                print(f"    ERROR: {err}")
            for warn in res.get("warnings", []):
                print(f"    WARN:  {warn}")

    sys.exit(0 if overall_valid else 1)


if __name__ == "__main__":
    main()
