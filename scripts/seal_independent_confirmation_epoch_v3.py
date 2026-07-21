#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


BASE = Path("research/independent_underlying_confirmation_v3")
SAFETY_FLAGS = {"read_only": True, "is_order_action": False, "broker_api_called": False, "execution_eligibility": False, "allowed_for_live_execution": False}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    path.with_suffix(path.suffix + ".sha256").write_text(f"{sha256_file(path)}  {path.name}\n")


def readiness(manifest: dict[str, Any]) -> dict[str, Any]:
    sessions = manifest.get("sessions", [])
    dates = [date.fromisoformat(row["session_date"]) for row in sessions]
    span = (max(dates) - min(dates)).days if dates else 0
    return {"eligible_sessions": len(sessions), "calendar_span_days": span, "session_gate_pass": len(sessions) >= 250, "calendar_gate_pass": span >= 365}


def main() -> int:
    manifest = json.loads((BASE / "independent_session_manifest.json").read_text())
    status = readiness(manifest)
    can_seal = status["session_gate_pass"] and status["calendar_gate_pass"]
    verdict = "INDEPENDENT_UNSEEN_EPOCH_SEALED_READY_FOR_EVALUATION" if can_seal else "WAITING_FOR_ADDITIONAL_UNSEEN_UNDERLYING_DATA"
    write_json(BASE / "data_acquisition" / "readiness_report.json", {**status, "verdict": verdict, "epoch_sealed": can_seal, "epoch_opened": False, "safety_flags": SAFETY_FLAGS})
    if can_seal:
        write_json(BASE / "data_acquisition" / "seal_certificate.json", {"sealed": True, "opened": False, "manifest_hash": manifest["session_list_hash"], "safety_flags": SAFETY_FLAGS})
    return 0 if can_seal else 2


if __name__ == "__main__":
    raise SystemExit(main())
