#!/usr/bin/env python3
"""Diagnose why tradebot is not producing executable trades.

This script parses one or more log files and extracts the signals that usually
explain candidate death:

- FINAL EMIT status
- executable count
- readiness/candidate/execution status
- primary blockers
- contract-resolution failures
- stale quote / spread / token hints

It is intentionally standalone and safe: it does not import the live trading
engine and does not call any broker API.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Any

KEY_PATTERNS = {
    "final_emit": re.compile(r"FINAL EMIT[: ]+(?P<body>.*)", re.IGNORECASE),
    "ranked_executable": re.compile(r"TB_RANKED_COUNT_EXECUTABLE\s+(?P<body>\{.*\})", re.IGNORECASE),
    "contract_failed": re.compile(r"CONTRACT_RESOLUTION_FAILED|unresolved_contract", re.IGNORECASE),
    "contract_fallback": re.compile(r"CONTRACT_RESOLUTION_FALLBACK", re.IGNORECASE),
    "advisory": re.compile(r"ADVISORY_ONLY", re.IGNORECASE),
    "ready_not_approved": re.compile(r"READY_NOT_APPROVED", re.IGNORECASE),
    "executable": re.compile(r"\bEXECUTABLE\b", re.IGNORECASE),
    "block": re.compile(r"\bBLOCK\b|non_executable|execution_allowed['\"]?\s*[:=]\s*False", re.IGNORECASE),
}

FIELD_PATTERNS = {
    "primary_blocker": re.compile(r"primary_blocker['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    "readiness": re.compile(r"readiness['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    "candidate_status": re.compile(r"candidate_status['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    "execution_status": re.compile(r"execution_status['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
    "quote_age_sec": re.compile(r"quote_age(?:_sec)?['\"]?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "spread_pct": re.compile(r"spread(?:_pct)?['\"]?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE),
    "tradingsymbol": re.compile(r"tradingsymbol['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]+|None|null)", re.IGNORECASE),
    "instrument_token": re.compile(r"instrument_token['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_\-]+|None|null)", re.IGNORECASE),
}


def _safe_jsonish(text: str) -> dict[str, Any] | None:
    """Best effort parse of dict-looking log fragments."""
    text = text.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        # Logs often print Python dicts with single quotes.
        import ast

        parsed = ast.literal_eval(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def iter_lines(paths: Iterable[Path]) -> Iterable[tuple[Path, int, str]]:
    for path in paths:
        if path.is_dir():
            yield from iter_lines(sorted(path.glob("*.log")))
            yield from iter_lines(sorted(path.glob("*.jsonl")))
            continue
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for lineno, line in enumerate(handle, start=1):
                    yield path, lineno, line.rstrip("\n")
        except Exception as exc:
            yield path, 0, f"__READ_ERROR__ {exc}"


def diagnose(paths: list[Path]) -> dict[str, Any]:
    counters: Counter[str] = Counter()
    field_values: dict[str, Counter[str]] = defaultdict(Counter)
    executable_counts: list[dict[str, Any]] = []
    final_emits: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []

    for path, lineno, line in iter_lines(paths):
        matched = False
        for name, pattern in KEY_PATTERNS.items():
            match = pattern.search(line)
            if match:
                counters[name] += 1
                matched = True
                if name == "ranked_executable":
                    payload = _safe_jsonish(match.group("body")) or {"raw": match.group("body")}
                    executable_counts.append({"file": str(path), "line": lineno, **payload})
                elif name == "final_emit":
                    final_emits.append({"file": str(path), "line": lineno, "body": match.group("body")})

        for field, pattern in FIELD_PATTERNS.items():
            for match in pattern.finditer(line):
                value = str(match.group(1)).strip("'\",}")
                field_values[field][value] += 1
                matched = True

        if matched and len(evidence) < 200:
            evidence.append({"file": str(path), "line": lineno, "text": line[:500]})

    zero_executable_symbols = []
    for row in executable_counts:
        count = row.get("count")
        try:
            if int(count) == 0:
                zero_executable_symbols.append(row.get("symbol", "UNKNOWN"))
        except Exception:
            pass

    likely_causes: list[str] = []
    if counters["contract_failed"]:
        likely_causes.append("contract_resolution_failure")
    if field_values["quote_age_sec"]:
        high_quote_age = [float(v) for v in field_values["quote_age_sec"] if _is_float(v) and float(v) > 3.0]
        if high_quote_age:
            likely_causes.append("stale_quote_age")
    if counters["advisory"] or counters["ready_not_approved"]:
        likely_causes.append("gating_or_approval_block")
    if zero_executable_symbols:
        likely_causes.append("ranker_produced_zero_executable")
    if field_values["tradingsymbol"].get("None") or field_values["instrument_token"].get("None"):
        likely_causes.append("missing_contract_identity")

    return {
        "summary": dict(counters),
        "likely_causes": sorted(set(likely_causes)),
        "field_values": {k: dict(v.most_common(20)) for k, v in field_values.items()},
        "zero_executable_symbols": sorted(set(str(x) for x in zero_executable_symbols)),
        "executable_counts": executable_counts[-50:],
        "final_emits": final_emits[-50:],
        "evidence": evidence,
    }


def _is_float(value: str) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose no executable trades from tradebot logs.")
    parser.add_argument("paths", nargs="*", default=["logs"], help="Log files or directories. Defaults to logs/")
    parser.add_argument("--json", action="store_true", help="Print full JSON output")
    args = parser.parse_args()

    result = diagnose([Path(p) for p in args.paths])

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0

    print("# No Executable Trades Diagnostic")
    print()
    print("## Summary")
    for key, value in result["summary"].items():
        print(f"- {key}: {value}")

    print()
    print("## Likely Causes")
    if result["likely_causes"]:
        for cause in result["likely_causes"]:
            print(f"- {cause}")
    else:
        print("- No obvious cause detected from available log lines.")

    print()
    print("## Top Field Values")
    for field, values in result["field_values"].items():
        print(f"### {field}")
        for value, count in values.items():
            print(f"- {value}: {count}")

    print()
    print("## Zero Executable Symbols")
    if result["zero_executable_symbols"]:
        for symbol in result["zero_executable_symbols"]:
            print(f"- {symbol}")
    else:
        print("- None detected")

    print()
    print("## Recent FINAL EMIT Lines")
    for row in result["final_emits"][-20:]:
        print(f"- {row['file']}:{row['line']} {row['body']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
