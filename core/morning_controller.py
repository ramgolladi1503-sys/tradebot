"""Read-only, resumable morning readiness state machine.

The controller is deliberately an orchestrator, not a broker client.  It
records independently supplied stage evidence and only advances when a stage
has a PASS record bound to the current frozen inputs.  Missing evidence blocks
instead of triggering an implicit network, order, or credential operation.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

STAGES = ("DISCOVER_SOURCE", "VERIFY_RELEASE", "CERTIFY_RELEASE_IF_REQUIRED", "INSTRUMENT_MASTER", "STORAGE_CLOCK", "AUTH", "BROKER_READ", "WEBSOCKET", "MARKET_DATA", "MROS", "TRUTH_FEED", "ARM_OBSERVER", "OBSERVE", "VERIFY_LIVE")
TERMINAL = frozenset({"PASS", "WAITING_HUMAN_AUTH", "WAITING_FOR_MARKET_DATA", "BLOCKED", "NOT_APPLICABLE"})
ALLOWED = TERMINAL | {"PENDING", "RUNNING"}


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class MorningController:
    def __init__(self, state_root: Path): self.state_root = Path(state_root)

    def state_path(self, session_date: str) -> Path:
        return self.state_root / session_date / "morning_controller_state.json"

    @staticmethod
    def evidence_from_governor(plan: object) -> dict[str, dict[str, object]]:
        """Adapt the existing MROS governor's read-only plan, never its booleans.

        The governor owns release, storage, instrument, auth, Truth Feed, and
        broker-write-boundary evaluation. This adapter maps its concrete states
        to controller stages; observer arming remains blocked until a separate
        existing launch-plan artifact is supplied.
        """
        value = plan.to_dict() if hasattr(plan, "to_dict") else dict(plan)
        ready = value.get("final_state") == "READY_FOR_GOVERNED_READ_ONLY_SESSION"
        def status(condition: bool, *, auth: bool = False) -> str:
            if condition: return "PASS"
            return "WAITING_HUMAN_AUTH" if auth else "BLOCKED"
        return {
            "DISCOVER_SOURCE": {"status": status(bool(value.get("candidate_sha")))},
            "VERIFY_RELEASE": {"status": status(bool(value.get("certified_release_sha")) and value.get("candidate_sha") == value.get("certified_release_sha"))},
            "CERTIFY_RELEASE_IF_REQUIRED": {"status": "NOT_APPLICABLE" if ready else "BLOCKED"},
            "INSTRUMENT_MASTER": {"status": status(str(value.get("instrument_master_state", "")).startswith("READY"))},
            "STORAGE_CLOCK": {"status": status(str(value.get("storage_state", "READY")).startswith("READY") and bool(value.get("session_root")))},
            "AUTH": {"status": status(value.get("auth_state") == "AUTH_TOKEN_PRESENT_UNVERIFIED", auth=True)},
            "BROKER_READ": {"status": "BLOCKED"},
            "WEBSOCKET": {"status": "BLOCKED"},
            "MARKET_DATA": {"status": "WAITING_FOR_MARKET_DATA"},
            "MROS": {"status": status(ready)},
            "TRUTH_FEED": {"status": status(str(value.get("truth_feed_state", "")).startswith("READY"))},
            "ARM_OBSERVER": {"status": "BLOCKED"}, "OBSERVE": {"status": "PENDING"}, "VERIFY_LIVE": {"status": "PENDING"},
        }

    def _checked_stage_evidence(self, stage: str, supplied: Mapping[str, object], *, session_date: str, source_sha: str) -> dict[str, object]:
        evidence_path = supplied.get("evidence_path")
        evidence_sha = supplied.get("evidence_sha256")
        if not isinstance(evidence_path, str) or not isinstance(evidence_sha, str):
            raise ValueError("stage_evidence_identity_missing")
        path = Path(evidence_path)
        resolved_path = path.resolve()
        governed_root = self.state_root.resolve()
        if resolved_path != governed_root and governed_root not in resolved_path.parents:
            raise ValueError("stage_evidence_path_outside_governed_root")
        raw = resolved_path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != evidence_sha:
            raise ValueError("stage_evidence_hash_mismatch")
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("stage") != stage or payload.get("session_date") != session_date or payload.get("source_sha") != source_sha:
            raise ValueError("stage_evidence_scope_mismatch")
        if payload.get("read_only") is not True or payload.get("broker_api_called") is not False or payload.get("order_authority") is not False:
            raise ValueError("stage_evidence_safety_contract_failed")
        if any(payload.get(key) != 0 for key in ("orders_placed", "orders_modified", "orders_cancelled")):
            raise ValueError("stage_evidence_order_count_nonzero")
        if payload.get("status") not in {"PASS", "WAITING_HUMAN_AUTH", "WAITING_FOR_MARKET_DATA", "NOT_APPLICABLE"}:
            raise ValueError("stage_evidence_status_invalid")
        return {"status": payload["status"], "evidence_path": str(resolved_path), "evidence_sha256": evidence_sha}

    def run(self, *, session_date: str, source_sha: str, config_sha: str, instrument_sha: str,
            evidence: Mapping[str, Mapping[str, object]] | None = None, trusted_internal: bool = False) -> dict:
        evidence = evidence or {}; path = self.state_path(session_date)
        inputs = {"source_sha": source_sha, "config_sha": config_sha, "instrument_sha": instrument_sha}
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        same_inputs = old.get("inputs") == inputs
        states = old.get("stages", {}) if same_inputs else {}
        output = {}
        blocked = False
        for stage in STAGES:
            prior = states.get(stage, {})
            supplied = evidence.get(stage)
            if blocked:
                output[stage] = {"status": "PENDING", "reason": "upstream_not_pass"}; continue
            if prior.get("status") == "PASS" and prior.get("inputs_sha256") == _sha(json.dumps(inputs, sort_keys=True)):
                output[stage] = prior; continue
            if not isinstance(supplied, Mapping):
                output[stage] = {"status": "WAITING_HUMAN_AUTH" if stage == "AUTH" else "BLOCKED", "reason": "independent_stage_evidence_required"}; blocked = True; continue
            try:
                checked = supplied if trusted_internal else self._checked_stage_evidence(stage, supplied, session_date=session_date, source_sha=source_sha)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                output[stage] = {"status": "BLOCKED", "reason": str(exc)}; blocked = True; continue
            status = checked.get("status")
            if status not in {"PASS", "WAITING_HUMAN_AUTH", "WAITING_FOR_MARKET_DATA", "NOT_APPLICABLE"}:
                output[stage] = {"status": "BLOCKED", "reason": "invalid_or_nonpass_stage_evidence"}; blocked = True; continue
            output[stage] = {**checked, "inputs_sha256": _sha(json.dumps(inputs, sort_keys=True)), "recorded_at": datetime.now(timezone.utc).isoformat()}
            if status != "PASS": blocked = True
        result = {"schema_version": 1, "session_date": session_date, "inputs": inputs, "stages": output,
                  "session_classification": "FULL" if all(x["status"] == "PASS" for x in output.values()) else "PARTIAL_SESSION",
                  "read_only": True, "broker_api_called": False, "broker_write_authority": False, "order_authority": False,
                  "paper_authorized": False, "live_authorized": False, "orders_placed": 0, "orders_modified": 0, "orders_cancelled": 0}
        _write(path, result); return result
