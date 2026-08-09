#!/usr/bin/env python3
"""Audit replay underlying corpus integrity before cache construction.

Requires exactly one UNDERLYING file per requested instrument family per session.
Options/ticks are ignored for this gate. Any duplicate or missing requested
underlying session fails closed. Research-only; no certification/runtime authority.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def audit(index: dict, families: list[str]) -> dict:
    families = [x.upper() for x in families]
    sessions = sorted({str(x.get("date")) for x in index.get("files", []) if x.get("date") not in (None, "", "UNKNOWN")})
    counts: dict[tuple[str, str], int] = defaultdict(int)
    paths: dict[tuple[str, str], list[str]] = defaultdict(list)
    ignored_non_underlying = 0

    for item in index.get("files", []):
        if item.get("dataset_kind") != "UNDERLYING":
            ignored_non_underlying += 1
            continue
        family = str(item.get("instrument_family", "UNKNOWN")).upper()
        date = str(item.get("date", "UNKNOWN"))
        if family not in families or date in ("", "UNKNOWN", "None"):
            continue
        key = (date, family)
        counts[key] += 1
        paths[key].append(str(item.get("path", "")))

    missing = []
    duplicates = []
    for date in sessions:
        for family in families:
            n = counts.get((date, family), 0)
            if n == 0:
                missing.append({"date": date, "family": family})
            elif n > 1:
                duplicates.append({"date": date, "family": family, "count": n, "paths": sorted(paths[(date, family)])})

    expected = len(sessions) * len(families)
    present_unique = sum(1 for date in sessions for family in families if counts.get((date, family), 0) == 1)
    status = "PASS" if not missing and not duplicates and sessions else "FAIL"
    return {
        "schema_version": "kite-replay-underlying-integrity-v1",
        "status": status,
        "families": families,
        "sessions": len(sessions),
        "expected_underlying_session_files": expected,
        "unique_underlying_session_files": present_unique,
        "missing": missing,
        "duplicates": duplicates,
        "ignored_non_underlying_files": ignored_non_underlying,
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", required=True)
    p.add_argument("--require-family", action="append", default=["NIFTY", "BANKNIFTY", "SENSEX"])
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    index = json.loads(Path(args.index).read_text(encoding="utf-8"))
    result = audit(index, args.require_family)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "status", "sessions", "expected_underlying_session_files",
        "unique_underlying_session_files", "ignored_non_underlying_files",
        "runtime_authority"
    )}, indent=2))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
