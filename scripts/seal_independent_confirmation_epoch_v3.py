#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any


BASE = Path("research/independent_underlying_confirmation_v3")
ACQ = BASE / "data_acquisition"
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
    ordered = manifest.get("sessions", [])
    first = ordered[0]["session_date"] if ordered else None
    last = ordered[-1]["session_date"] if ordered else None
    report = {
        **status,
        "verdict": verdict,
        "first_eligible_session": first,
        "last_eligible_session": last,
        "manifest_hash": manifest.get("session_list_hash"),
        "epoch_sealed": can_seal,
        "epoch_opened": False,
        "safety_flags": SAFETY_FLAGS,
    }
    write_json(ACQ / "readiness_report.json", report)
    if can_seal:
        external_hashes = []
        for row in ordered:
            for symbol, path in sorted(row["symbol_file_paths"].items()):
                external_hashes.append(
                    {
                        "session_date": row["session_date"],
                        "symbol": symbol,
                        "path": path,
                        "sha256": row["file_sha256_hashes"][symbol],
                    }
                )
        sealed_contract = {
            "epoch_type": "INDEPENDENT_HISTORICAL_CONFIRMATION_EPOCH_V3",
            "sealed": True,
            "opened": False,
            "first_session": first,
            "last_session": last,
            "eligible_sessions": len(ordered),
            "calendar_span_days": status["calendar_span_days"],
            "manifest_hash": manifest["session_list_hash"],
            "strategy_candidate_counts_calculated": False,
            "strategy_outcomes_calculated": False,
            "safety_flags": SAFETY_FLAGS,
        }
        write_json(ACQ / "sealed_epoch_contract.json", sealed_contract)
        write_json(ACQ / "sealed_session_manifest.json", manifest)
        write_json(ACQ / "sealed_external_hash_manifest.json", {"files": external_hashes, "file_count": len(external_hashes), "safety_flags": SAFETY_FLAGS})
        write_json(ACQ / "seal_certificate.json", {"sealed": True, "opened": False, "manifest_hash": manifest["session_list_hash"], "sealed_session_manifest_hash": sha256_file(ACQ / "sealed_session_manifest.json"), "safety_flags": SAFETY_FLAGS})
    return 0 if can_seal else 2


if __name__ == "__main__":
    raise SystemExit(main())
