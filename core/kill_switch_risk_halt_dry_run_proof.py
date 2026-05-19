"""Kill switch and risk halt dry-run proof.

This module proves that kill-switch/risk-halt evidence is respected around a
broker reconciliation dry-run proof. It is read-only and does not call brokers,
submit orders, mutate ledgers, write files, or wire runtime behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.broker_reconciliation_dry_run_proof import BROKER_RECON_DRY_RUN_PROVEN

KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF_SCHEMA_VERSION = 1

KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN = "KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN"
KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED = "KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED"


def _to_mapping(value: Any) -> Mapping[str, Any] | None:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        if isinstance(payload, Mapping):
            return payload
    return None


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _validate_non_action(source: str, payload: Mapping[str, Any], blockers: list[str]) -> None:
    if _bool(payload.get("broker_order_action"), default=False):
        blockers.append(f"{source}_BROKER_ORDER_ACTION_REJECTED")
    if _bool(payload.get("live_order_action"), default=False):
        blockers.append(f"{source}_LIVE_ORDER_ACTION_REJECTED")
    if _bool(payload.get("is_order_action"), default=False):
        blockers.append(f"{source}_ORDER_ACTION_REJECTED")
    if _bool(payload.get("append"), default=False):
        blockers.append(f"{source}_APPEND_TRUE_REJECTED")


@dataclass(frozen=True)
class KillSwitchRiskHaltDryRunProof:
    schema_version: int
    state: str
    read_only: bool
    dry_run: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    payload_id: str | None
    kill_switch_active: bool | None
    risk_halt_active: bool | None
    halt_reason: str | None
    proof_mode: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reconciliation_proof: dict[str, Any]
    safety_evidence: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reconciliation_proof"] = dict(self.reconciliation_proof)
        payload["safety_evidence"] = dict(self.safety_evidence)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_kill_switch_risk_halt_dry_run_proof(
    *,
    reconciliation_proof: Any,
    safety_evidence: Any,
) -> KillSwitchRiskHaltDryRunProof:
    """Build a read-only proof that kill switch/risk halt evidence blocks dry-run progress."""

    blockers: list[str] = []
    warnings: list[str] = []

    recon = _to_mapping(reconciliation_proof)
    safety = _to_mapping(safety_evidence)

    if recon is None:
        blockers.append("RECONCILIATION_PROOF_MISSING")
        recon = {}
    else:
        blockers.extend(_list_of_strings(recon.get("blockers")))
        warnings.extend(_list_of_strings(recon.get("warnings")))
        _validate_non_action("RECONCILIATION_PROOF", recon, blockers)
        if str(recon.get("state") or "") != BROKER_RECON_DRY_RUN_PROVEN:
            blockers.append("RECONCILIATION_PROOF_NOT_PROVEN")
        if not _bool(recon.get("read_only"), default=False):
            blockers.append("RECONCILIATION_PROOF_NOT_READ_ONLY")
        if not _bool(recon.get("dry_run"), default=False):
            blockers.append("RECONCILIATION_PROOF_DRY_RUN_REQUIRED")

    if safety is None:
        blockers.append("SAFETY_EVIDENCE_MISSING")
        safety = {}
    else:
        blockers.extend(_list_of_strings(safety.get("blockers")))
        warnings.extend(_list_of_strings(safety.get("warnings")))
        _validate_non_action("SAFETY_EVIDENCE", safety, blockers)
        if not _bool(safety.get("read_only"), default=False):
            blockers.append("SAFETY_EVIDENCE_NOT_READ_ONLY")
        if not _bool(safety.get("dry_run"), default=False):
            blockers.append("SAFETY_EVIDENCE_DRY_RUN_REQUIRED")

    kill_switch_present = "kill_switch_active" in safety
    risk_halt_present = "risk_halt_active" in safety
    if not kill_switch_present:
        blockers.append("KILL_SWITCH_SIGNAL_MISSING")
    if not risk_halt_present:
        blockers.append("RISK_HALT_SIGNAL_MISSING")

    kill_switch_active = _bool(safety.get("kill_switch_active"), default=False) if kill_switch_present else None
    risk_halt_active = _bool(safety.get("risk_halt_active"), default=False) if risk_halt_present else None
    halt_reason = _text(safety.get("halt_reason"))
    proof_mode = str(safety.get("proof_mode") or "").strip().upper()

    if proof_mode not in {"ASSERT_BLOCKED", "ASSERT_CLEAR"}:
        blockers.append("PROOF_MODE_UNSUPPORTED")

    if proof_mode == "ASSERT_BLOCKED":
        if not bool(kill_switch_active or risk_halt_active):
            blockers.append("EXPECTED_HALT_NOT_ACTIVE")
        if halt_reason is None:
            blockers.append("HALT_REASON_REQUIRED_WHEN_BLOCKED")
    elif proof_mode == "ASSERT_CLEAR":
        if bool(kill_switch_active or risk_halt_active):
            blockers.append("EXPECTED_CLEAR_BUT_HALT_ACTIVE")

    payload_id = _text(recon.get("payload_id")) or _text(safety.get("payload_id"))
    if payload_id is None:
        blockers.append("PAYLOAD_ID_MISSING")
    else:
        safety_payload_id = _text(safety.get("payload_id"))
        recon_payload_id = _text(recon.get("payload_id"))
        if safety_payload_id and recon_payload_id and safety_payload_id != recon_payload_id:
            blockers.append("PAYLOAD_ID_MISMATCH")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    proven = not normalized_blockers

    return KillSwitchRiskHaltDryRunProof(
        schema_version=KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF_SCHEMA_VERSION,
        state=KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN if proven else KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED,
        read_only=True,
        dry_run=bool(_bool(recon.get("dry_run"), default=False) and _bool(safety.get("dry_run"), default=False)),
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        payload_id=payload_id,
        kill_switch_active=kill_switch_active,
        risk_halt_active=risk_halt_active,
        halt_reason=halt_reason,
        proof_mode=proof_mode or "UNKNOWN",
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reconciliation_proof=dict(recon),
        safety_evidence=dict(safety),
        metadata={
            "proof": "kill_switch_risk_halt_dry_run_proof_v1",
            "scope": "read_only_no_broker_calls_no_order_submission_no_runtime_wiring",
            "schema_version": KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF_SCHEMA_VERSION,
        },
    )


__all__ = [
    "KILL_SWITCH_RISK_HALT_DRY_RUN_BLOCKED",
    "KILL_SWITCH_RISK_HALT_DRY_RUN_PROOF_SCHEMA_VERSION",
    "KILL_SWITCH_RISK_HALT_DRY_RUN_PROVEN",
    "KillSwitchRiskHaltDryRunProof",
    "build_kill_switch_risk_halt_dry_run_proof",
]
