"""Paper session evidence pack assembler.

This module composes already-built paper trading reports into one deterministic,
JSON-friendly evidence pack. It does not run a session, read/write files, mutate
orders or ledgers, call brokers, or wire runtime/dashboard behavior.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping

PAPER_SESSION_EVIDENCE_PACK_SCHEMA_VERSION = 1

EVIDENCE_PACK_READY = "EVIDENCE_PACK_READY"
EVIDENCE_PACK_BLOCKED = "EVIDENCE_PACK_BLOCKED"


class PaperSessionEvidencePackError(ValueError):
    """Raised when evidence pack configuration is invalid."""


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


def _as_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _list_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    return ()


def _dedupe(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))


def _normalize_optional_reports(value: Any, *, section_name: str, blockers: list[str]) -> tuple[dict[str, Any], ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        blockers.append(f"{section_name.upper()}_NOT_A_LIST")
        return ()

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        payload = _to_mapping(item)
        if payload is None:
            blockers.append(f"{section_name.upper()}_{index}_INVALID")
            continue
        _validate_safety_flags(payload, blockers, prefix=f"{section_name.upper()}_{index}")
        normalized.append(dict(payload))
    return tuple(normalized)


def _validate_safety_flags(payload: Mapping[str, Any], blockers: list[str], *, prefix: str) -> None:
    if _bool(payload.get("broker_order_action"), default=False):
        blockers.append(f"{prefix}_BROKER_ORDER_ACTION_REJECTED")
    if _bool(payload.get("live_order_action"), default=False):
        blockers.append(f"{prefix}_LIVE_ORDER_ACTION_REJECTED")
    if _bool(payload.get("is_order_action"), default=False):
        blockers.append(f"{prefix}_ORDER_ACTION_REJECTED")
    if _bool(payload.get("append"), default=False):
        blockers.append(f"{prefix}_APPEND_TRUE_REJECTED")


@dataclass(frozen=True)
class PaperSessionEvidencePack:
    schema_version: int
    state: str
    read_only: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    session_id: str | None
    evidence_complete: bool
    artifact_count: int
    section_names: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    reasons: tuple[str, ...]
    evidence: dict[str, Any]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["section_names"] = list(self.section_names)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["reasons"] = list(self.reasons)
        payload["evidence"] = dict(self.evidence)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_paper_session_evidence_pack(
    *,
    session_gate_report: Any,
    risk_ledger_snapshot: Any,
    paper_decision_reports: Any = None,
    paper_order_records: Any = None,
    fill_decisions: Any = None,
    extra_artifacts: Mapping[str, Any] | None = None,
) -> PaperSessionEvidencePack:
    """Build a deterministic paper session evidence pack from supplied reports."""

    blockers: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    gate = _to_mapping(session_gate_report)
    ledger = _to_mapping(risk_ledger_snapshot)

    if gate is None:
        blockers.append("SESSION_GATE_REPORT_MISSING")
        gate = {}
    else:
        blockers.extend(_list_of_strings(gate.get("blockers")))
        warnings.extend(_list_of_strings(gate.get("warnings")))
        _validate_safety_flags(gate, blockers, prefix="SESSION_GATE_REPORT")
        if str(gate.get("state") or "") != "SESSION_GATE_PASS":
            blockers.append("SESSION_GATE_NOT_PASS")
        if not _bool(gate.get("read_only"), default=False):
            blockers.append("SESSION_GATE_NOT_READ_ONLY")
        if not _bool(gate.get("evidence_complete"), default=False):
            blockers.append("SESSION_GATE_EVIDENCE_INCOMPLETE")

    if ledger is None:
        blockers.append("RISK_LEDGER_SNAPSHOT_MISSING")
        ledger = {}
    else:
        blockers.extend(_list_of_strings(ledger.get("blockers")))
        warnings.extend(_list_of_strings(ledger.get("warnings")))
        _validate_safety_flags(ledger, blockers, prefix="RISK_LEDGER_SNAPSHOT")
        if not _bool(ledger.get("read_only"), default=False):
            blockers.append("RISK_LEDGER_NOT_READ_ONLY")
        if _bool(ledger.get("risk_halt_active"), default=False):
            blockers.append("RISK_LEDGER_HALT_ACTIVE")

    session_id = _text(gate.get("session_id")) if gate else None
    if session_id is None:
        blockers.append("SESSION_ID_MISSING")

    decisions = _normalize_optional_reports(paper_decision_reports, section_name="paper_decision_reports", blockers=blockers)
    orders = _normalize_optional_reports(paper_order_records, section_name="paper_order_records", blockers=blockers)
    fills = _normalize_optional_reports(fill_decisions, section_name="fill_decisions", blockers=blockers)
    artifacts = dict(extra_artifacts or {})

    if not isinstance(artifacts, dict):
        raise PaperSessionEvidencePackError("extra_artifacts_must_be_mapping")

    for key, value in artifacts.items():
        if not str(key or "").strip():
            blockers.append("EXTRA_ARTIFACT_KEY_EMPTY")
        payload = _to_mapping(value)
        if payload is not None:
            _validate_safety_flags(payload, blockers, prefix=f"EXTRA_ARTIFACT_{str(key).upper()}")

    evidence = {
        "session_gate_report": dict(gate),
        "risk_ledger_snapshot": dict(ledger),
        "paper_decision_reports": list(decisions),
        "paper_order_records": list(orders),
        "fill_decisions": list(fills),
        "extra_artifacts": artifacts,
    }
    section_names = tuple(sorted(evidence.keys()))
    artifact_count = 2 + len(decisions) + len(orders) + len(fills) + len(artifacts)

    gate_order_count = _as_int(gate.get("paper_order_count"), default=0) if gate else 0
    gate_fill_count = _as_int(gate.get("paper_fill_count"), default=0) if gate else 0
    ledger_open_count = _as_int(ledger.get("open_position_count"), default=0) if ledger else 0

    if orders and len(orders) > gate_order_count:
        blockers.append("EVIDENCE_ORDERS_EXCEED_GATE_ORDER_COUNT")
    if fills and len(fills) > gate_fill_count:
        blockers.append("EVIDENCE_FILLS_EXCEED_GATE_FILL_COUNT")
    if ledger_open_count < 0:
        blockers.append("RISK_LEDGER_OPEN_POSITION_COUNT_NEGATIVE")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    ready = not normalized_blockers
    if ready:
        state = EVIDENCE_PACK_READY
        reasons.append("paper_session_evidence_pack_ready")
    else:
        state = EVIDENCE_PACK_BLOCKED
        reasons.append("paper_session_evidence_pack_blocked")

    return PaperSessionEvidencePack(
        schema_version=PAPER_SESSION_EVIDENCE_PACK_SCHEMA_VERSION,
        state=state,
        read_only=True,
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        session_id=session_id,
        evidence_complete=ready,
        artifact_count=int(artifact_count),
        section_names=section_names,
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        reasons=tuple(sorted({reason for reason in reasons if reason})),
        evidence=evidence,
        metadata={
            "evidence_pack": "paper_session_evidence_pack_v1",
            "scope": "read_only_no_runtime_wiring_no_broker_calls_no_order_mutation_no_persistence",
            "schema_version": PAPER_SESSION_EVIDENCE_PACK_SCHEMA_VERSION,
        },
    )


__all__ = [
    "EVIDENCE_PACK_BLOCKED",
    "EVIDENCE_PACK_READY",
    "PAPER_SESSION_EVIDENCE_PACK_SCHEMA_VERSION",
    "PaperSessionEvidencePack",
    "PaperSessionEvidencePackError",
    "build_paper_session_evidence_pack",
]
