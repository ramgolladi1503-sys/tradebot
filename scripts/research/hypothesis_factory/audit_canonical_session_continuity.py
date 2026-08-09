#!/usr/bin/env python3
"""Audit canonical underlying cache continuity before hypothesis screening.

Checks one coherent intraday series per session/instrument, duplicate timestamps,
bar-count distribution, timestamp ordering, and cross-session contamination.
Research-only; never certifies edge or grants runtime/broker authority.
"""
from __future__ import annotations

import argparse, csv, json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def audit(path: Path, instrument: str) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8", newline="")))
    instrument = instrument.upper()
    sessions: dict[str, list[dict[str, str]]] = defaultdict(list)
    duplicate_keys: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    bad_instrument = 0
    bad_timestamp = 0

    for row in rows:
        if str(row.get("instrument", "")).upper() != instrument:
            bad_instrument += 1
            continue
        ts = str(row.get("timestamp", ""))
        if len(ts) < 10:
            bad_timestamp += 1
            continue
        session = ts[:10]
        key = (session, ts)
        if key in seen:
            duplicate_keys.append(key)
        else:
            seen.add(key)
        sessions[session].append(row)

    counts = {s: len(v) for s, v in sessions.items()}
    hist = Counter(counts.values())
    unsorted_sessions = []
    for s, vals in sessions.items():
        stamps = [str(x.get("timestamp", "")) for x in vals]
        if stamps != sorted(stamps):
            unsorted_sessions.append(s)

    session_dates = sorted(sessions)
    status = "PASS"
    reasons = []
    if duplicate_keys:
        status = "FAIL"
        reasons.append("DUPLICATE_SESSION_TIMESTAMPS")
    if bad_instrument:
        status = "FAIL"
        reasons.append("CROSS_INSTRUMENT_ROWS")
    if bad_timestamp:
        status = "FAIL"
        reasons.append("INVALID_TIMESTAMPS")
    if unsorted_sessions:
        status = "FAIL"
        reasons.append("UNSORTED_SESSION_ROWS")

    return {
        "status": status,
        "reasons": reasons,
        "instrument": instrument,
        "input_rows": len(rows),
        "sessions": len(sessions),
        "first_session": session_dates[0] if session_dates else None,
        "last_session": session_dates[-1] if session_dates else None,
        "duplicate_session_timestamps": len(duplicate_keys),
        "bad_instrument_rows": bad_instrument,
        "bad_timestamp_rows": bad_timestamp,
        "unsorted_sessions": len(unsorted_sessions),
        "min_bars_per_session": min(counts.values()) if counts else 0,
        "max_bars_per_session": max(counts.values()) if counts else 0,
        "bar_count_distribution": dict(sorted(hist.items())),
        "sessions_below_70_bars": sum(1 for c in counts.values() if c < 70),
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
        "certification": "NOT_CERTIFIED",
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True)
    p.add_argument("--instrument", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args(argv)
    result = audit(Path(args.input), args.instrument)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
