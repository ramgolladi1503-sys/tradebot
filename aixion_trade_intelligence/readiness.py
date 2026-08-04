from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class CanaryReadiness:
    ready: bool
    verdict: str
    checks: dict[str, dict[str, object]]

    def to_record(self) -> dict[str, object]:
        return {
            "ready": self.ready,
            "verdict": self.verdict,
            "checks": self.checks,
        }


def _required_mapping(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = payload.get(name)
    if not isinstance(value, Mapping):
        raise ValueError(f"missing_{name}")
    return value


def evaluate_canary_readiness(config_path: str | Path) -> CanaryReadiness:
    config_file = Path(config_path)
    payload = json.loads(config_file.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("config_must_be_object")
    mode = str(payload.get("mode") or "").strip().upper()
    if mode not in {"PAPER", "SHADOW"}:
        raise ValueError("canary_mode_must_be_paper_or_shadow")
    evidence_root = Path(str(payload.get("evidence_root") or "")).expanduser()
    if not str(evidence_root):
        raise ValueError("missing_evidence_root")
    storage = _required_mapping(payload, "storage")
    expected_session_bytes = int(storage.get("expected_session_bytes") or 0)
    safety_factor = float(storage.get("safety_factor") or 0.0)
    if expected_session_bytes <= 0:
        raise ValueError("expected_session_bytes_must_be_measured_positive")
    if safety_factor < 1.0:
        raise ValueError("safety_factor_must_be_at_least_one")
    required_bytes = int(expected_session_bytes * safety_factor)

    reference_files = payload.get("point_in_time_reference_files")
    if not isinstance(reference_files, list) or not reference_files:
        raise ValueError("point_in_time_reference_files_required")

    checks: dict[str, dict[str, object]] = {}
    evidence_root.mkdir(parents=True, exist_ok=True)
    probe = evidence_root / ".aixion_write_probe"
    writable = False
    try:
        probe.write_text("ok", encoding="utf-8")
        writable = probe.read_text(encoding="utf-8") == "ok"
    finally:
        probe.unlink(missing_ok=True)
    checks["evidence_root_writable"] = {
        "passed": writable,
        "path": str(evidence_root.resolve()),
    }

    disk = shutil.disk_usage(evidence_root)
    storage_passed = disk.free >= required_bytes
    checks["storage_capacity"] = {
        "passed": storage_passed,
        "free_bytes": disk.free,
        "required_bytes": required_bytes,
        "expected_session_bytes": expected_session_bytes,
        "safety_factor": safety_factor,
    }

    missing_references: list[str] = []
    empty_references: list[str] = []
    resolved_references: list[str] = []
    for raw in reference_files:
        path = Path(str(raw)).expanduser()
        resolved_references.append(str(path))
        if not path.exists():
            missing_references.append(str(path))
        elif path.is_file() and path.stat().st_size == 0:
            empty_references.append(str(path))
    references_passed = not missing_references and not empty_references
    checks["point_in_time_references"] = {
        "passed": references_passed,
        "files": resolved_references,
        "missing": missing_references,
        "empty": empty_references,
    }

    checks["mode_boundary"] = {
        "passed": mode in {"PAPER", "SHADOW"},
        "mode": mode,
        "live_order_authority": False,
    }

    required_event_types = payload.get("required_event_types")
    event_contract_passed = (
        isinstance(required_event_types, list)
        and "SESSION_STARTED" in required_event_types
        and "SESSION_ENDED" in required_event_types
        and "FEED_TRUTH_UPDATED" in required_event_types
    )
    checks["event_contract"] = {
        "passed": event_contract_passed,
        "required_event_types": required_event_types,
    }

    ready = all(bool(check["passed"]) for check in checks.values())
    verdict = "READY_FOR_READ_ONLY_CANARY" if ready else "CANARY_BLOCKED"
    return CanaryReadiness(ready=ready, verdict=verdict, checks=checks)
