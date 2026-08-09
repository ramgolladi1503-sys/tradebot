#!/usr/bin/env python3
"""Fail-closed completeness audit for a locally downloaded historical corpus.

Consumes the local historical-session index and checks that the download has
sufficient total sessions and per-family underlying coverage before any cache,
screen, robustness, or certification work is allowed.

An optional remote-session manifest can be supplied to compare locally present
session dates against a separately captured Drive inventory. This script never
infers missing remote data and never upgrades research authority.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_family_requirement(value: str) -> tuple[str, int]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("family requirement must be FAMILY=COUNT")
    family, raw = value.split("=", 1)
    family = family.strip().upper()
    try:
        count = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("COUNT must be an integer") from exc
    if count < 0:
        raise argparse.ArgumentTypeError("COUNT must be >= 0")
    return family, count


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_remote_dates(payload: dict[str, Any]) -> set[str]:
    dates: set[str] = set()
    for key in ("session_dates", "dates", "sessions"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    dates.add(item)
                elif isinstance(item, dict) and item.get("date"):
                    dates.add(str(item["date"]))
    return {d for d in dates if d and d != "UNKNOWN"}


def audit(
    index: dict[str, Any],
    min_total_sessions: int,
    family_requirements: dict[str, int],
    remote_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = index.get("summary") or {}
    local_sessions = {
        str(s.get("date")) for s in (index.get("sessions") or [])
        if isinstance(s, dict) and s.get("date") and s.get("date") != "UNKNOWN"
    }
    underlying_sessions = summary.get("underlying_sessions") or {}

    failures: list[dict[str, Any]] = []
    if len(local_sessions) < min_total_sessions:
        failures.append({
            "code": "TOTAL_SESSION_COVERAGE_BELOW_MINIMUM",
            "observed": len(local_sessions),
            "required": min_total_sessions,
        })

    family_observed: dict[str, int] = {}
    for family, required in sorted(family_requirements.items()):
        dates = underlying_sessions.get(family) or []
        observed = len({str(d) for d in dates if d and d != "UNKNOWN"})
        family_observed[family] = observed
        if observed < required:
            failures.append({
                "code": "UNDERLYING_FAMILY_COVERAGE_BELOW_MINIMUM",
                "family": family,
                "observed": observed,
                "required": required,
            })

    remote_dates: set[str] = set()
    missing_remote_dates: list[str] = []
    if remote_manifest is not None:
        remote_dates = normalize_remote_dates(remote_manifest)
        missing_remote_dates = sorted(remote_dates - local_sessions)
        if missing_remote_dates:
            failures.append({
                "code": "REMOTE_SESSIONS_MISSING_LOCALLY",
                "remote_sessions": len(remote_dates),
                "local_sessions": len(local_sessions),
                "missing_count": len(missing_remote_dates),
            })

    status = "COMPLETE_FOR_REQUESTED_GATE" if not failures else "INCOMPLETE_DOWNLOAD"
    return {
        "schema_version": "tradebot-historical-download-completeness-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "local_root_count": len(index.get("roots") or []),
        "local_files": int(summary.get("files") or 0),
        "local_sessions": len(local_sessions),
        "family_underlying_sessions": family_observed,
        "requirements": {
            "min_total_sessions": min_total_sessions,
            "family_minimums": family_requirements,
        },
        "remote_manifest_supplied": remote_manifest is not None,
        "remote_sessions": len(remote_dates),
        "missing_remote_dates": missing_remote_dates,
        "failures": failures,
        "certification": "NOT_CERTIFIED",
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--index", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--min-total-sessions", type=int, default=20)
    p.add_argument("--require-family", action="append", default=[])
    p.add_argument("--remote-session-manifest", default="")
    args = p.parse_args(argv)

    index = load_json(Path(args.index))
    requirements = dict(parse_family_requirement(v) for v in args.require_family)
    remote = load_json(Path(args.remote_session_manifest)) if args.remote_session_manifest else None
    result = audit(index, args.min_total_sessions, requirements, remote)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "local_files": result["local_files"],
        "local_sessions": result["local_sessions"],
        "family_underlying_sessions": result["family_underlying_sessions"],
        "failures": result["failures"],
        "runtime_authority": "NONE",
    }, indent=2))
    return 0 if result["status"] == "COMPLETE_FOR_REQUESTED_GATE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
