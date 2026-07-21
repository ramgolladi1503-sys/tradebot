from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path


DEFAULT_MANIFEST = Path("research/prospective_structural_edge_v2/prospective_session_manifest.json")
DEFAULT_OUTPUT = Path("research/prospective_structural_edge_v2/prospective_lockbox_readiness.json")
SAFETY_FLAGS = {
    "read_only": True,
    "is_order_action": False,
    "broker_api_called": False,
    "execution_eligibility": False,
    "allowed_for_live_execution": False,
}


def calendar_span(first: str | None, last: str | None) -> int:
    if not first or not last:
        return 0
    return (datetime.strptime(last, "%Y%m%d") - datetime.strptime(first, "%Y%m%d")).days


def build_readiness(manifest: dict) -> dict:
    eligible = [session for session in manifest.get("sessions", []) if session.get("eligibility_status") == "ELIGIBLE_PROSPECTIVE_SESSION"]
    first = eligible[0]["session"] if eligible else None
    last = eligible[-1]["session"] if eligible else None
    span = calendar_span(first, last)
    blockers = []
    if len(eligible) < 80:
        blockers.append("INSUFFICIENT_ELIGIBLE_SESSIONS")
    if span < 120:
        blockers.append("INSUFFICIENT_CALENDAR_SPAN")
    return {
        "schema_version": 1,
        "epoch_id": manifest.get("epoch_id", "PROSPECTIVE_STRUCTURAL_EDGE_EPOCH_V2"),
        "eligible_sessions": len(eligible),
        "first_eligible_session": first,
        "last_eligible_session": last,
        "calendar_span_days": span,
        "remaining_sessions_required": max(0, 80 - len(eligible)),
        "remaining_calendar_days_required": max(0, 120 - span),
        "lockbox_seal_status": "READY_TO_SEAL" if not blockers else "NOT_READY",
        "blockers": blockers,
        "prospective_outcomes_inspected": False,
        "safety_flags": SAFETY_FLAGS,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    readiness = build_readiness(json.loads(args.manifest.read_text()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(readiness, indent=2, sort_keys=True) + "\n")
    return 0 if readiness["lockbox_seal_status"] == "READY_TO_SEAL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
