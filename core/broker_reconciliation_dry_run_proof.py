"""Broker reconciliation dry-run proof.

This module proves that a dry-run broker payload gate report matches a supplied
broker echo/receipt-like object without calling any broker or creating orders.
It is read-only and does not submit, modify, cancel, or exit orders.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from core.live_dry_run_broker_payload_gate import BROKER_PAYLOAD_DRY_RUN_APPROVED

BROKER_RECONCILIATION_DRY_RUN_PROOF_SCHEMA_VERSION = 1

BROKER_RECON_DRY_RUN_PROVEN = "BROKER_RECON_DRY_RUN_PROVEN"
BROKER_RECON_DRY_RUN_BLOCKED = "BROKER_RECON_DRY_RUN_BLOCKED"

RECONCILED_FIELDS: tuple[str, ...] = (
    "payload_id",
    "exchange",
    "tradingsymbol",
    "transaction_type",
    "order_type",
    "product",
    "variety",
    "validity",
    "quantity",
    "price",
    "trigger_price",
)


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


def _as_number_or_text(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    try:
        number = float(value)
    except Exception:
        text = _text(value)
        return text.upper() if text else None
    if number != number:
        return None
    if number.is_integer():
        return int(number)
    return round(number, 6)


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


def _normalize_recon_value(field: str, value: Any) -> Any:
    if field in {"exchange", "transaction_type", "order_type", "product", "validity"}:
        text = _text(value)
        return text.upper() if text else None
    if field == "variety":
        return _text(value)
    if field in {"quantity", "price", "trigger_price"}:
        return _as_number_or_text(value)
    return _text(value)


def _extract_gate_payload(gate_report: Mapping[str, Any], blockers: list[str]) -> Mapping[str, Any]:
    payload = gate_report.get("normalized_payload")
    if isinstance(payload, Mapping):
        return payload
    blockers.append("GATE_NORMALIZED_PAYLOAD_MISSING")
    return {}


@dataclass(frozen=True)
class BrokerReconciliationDryRunProof:
    schema_version: int
    state: str
    read_only: bool
    dry_run: bool
    is_order_action: bool
    append: bool
    broker_order_action: bool
    live_order_action: bool
    payload_id: str | None
    reconciled_fields: tuple[str, ...]
    mismatched_fields: tuple[str, ...]
    missing_receipt_fields: tuple[str, ...]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    gate_report: dict[str, Any]
    broker_receipt: dict[str, Any]
    field_comparison: dict[str, dict[str, Any]]
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reconciled_fields"] = list(self.reconciled_fields)
        payload["mismatched_fields"] = list(self.mismatched_fields)
        payload["missing_receipt_fields"] = list(self.missing_receipt_fields)
        payload["blockers"] = list(self.blockers)
        payload["warnings"] = list(self.warnings)
        payload["gate_report"] = dict(self.gate_report)
        payload["broker_receipt"] = dict(self.broker_receipt)
        payload["field_comparison"] = dict(self.field_comparison)
        payload["metadata"] = dict(self.metadata)
        return payload


def build_broker_reconciliation_dry_run_proof(
    *,
    gate_report: Any,
    broker_receipt: Any,
) -> BrokerReconciliationDryRunProof:
    """Build a read-only dry-run reconciliation proof."""

    blockers: list[str] = []
    warnings: list[str] = []

    gate = _to_mapping(gate_report)
    receipt = _to_mapping(broker_receipt)

    if gate is None:
        blockers.append("GATE_REPORT_MISSING")
        gate = {}
    else:
        blockers.extend(_list_of_strings(gate.get("blockers")))
        warnings.extend(_list_of_strings(gate.get("warnings")))
        if str(gate.get("state") or "") != BROKER_PAYLOAD_DRY_RUN_APPROVED:
            blockers.append("GATE_REPORT_NOT_APPROVED")
        if not _bool(gate.get("read_only"), default=False):
            blockers.append("GATE_REPORT_NOT_READ_ONLY")
        if not _bool(gate.get("dry_run"), default=False):
            blockers.append("GATE_REPORT_DRY_RUN_REQUIRED")

    if receipt is None:
        blockers.append("BROKER_RECEIPT_MISSING")
        receipt = {}
    else:
        blockers.extend(_list_of_strings(receipt.get("blockers")))
        warnings.extend(_list_of_strings(receipt.get("warnings")))

    for source, payload in (("GATE_REPORT", gate), ("BROKER_RECEIPT", receipt)):
        if _bool(payload.get("broker_order_action"), default=False):
            blockers.append(f"{source}_BROKER_ORDER_ACTION_REJECTED")
        if _bool(payload.get("live_order_action"), default=False):
            blockers.append(f"{source}_LIVE_ORDER_ACTION_REJECTED")
        if _bool(payload.get("is_order_action"), default=False):
            blockers.append(f"{source}_ORDER_ACTION_REJECTED")
        if _bool(payload.get("append"), default=False):
            blockers.append(f"{source}_APPEND_TRUE_REJECTED")

    if receipt and not _bool(receipt.get("dry_run"), default=False):
        blockers.append("BROKER_RECEIPT_DRY_RUN_REQUIRED")
    if receipt and _text(receipt.get("broker_order_id")):
        blockers.append("BROKER_RECEIPT_ORDER_ID_PRESENT")
    if receipt and _bool(receipt.get("submitted"), default=False):
        blockers.append("BROKER_RECEIPT_SUBMITTED_TRUE_REJECTED")

    gate_payload = _extract_gate_payload(gate, blockers)
    field_comparison: dict[str, dict[str, Any]] = {}
    mismatches: list[str] = []
    missing: list[str] = []

    for field in RECONCILED_FIELDS:
        expected = _normalize_recon_value(field, gate_payload.get(field))
        actual_raw = receipt.get(field)
        actual = _normalize_recon_value(field, actual_raw)
        field_comparison[field] = {
            "expected": expected,
            "actual": actual,
            "matched": expected == actual,
        }
        if field not in receipt:
            missing.append(field)
        elif expected != actual:
            mismatches.append(field)

    if missing:
        blockers.append("BROKER_RECEIPT_FIELDS_MISSING")
    if mismatches:
        blockers.append("BROKER_RECEIPT_FIELD_MISMATCH")

    normalized_blockers = _dedupe(blockers)
    normalized_warnings = _dedupe(warnings)
    proven = not normalized_blockers

    payload_id = _text(gate_payload.get("payload_id")) or _text(receipt.get("payload_id"))

    return BrokerReconciliationDryRunProof(
        schema_version=BROKER_RECONCILIATION_DRY_RUN_PROOF_SCHEMA_VERSION,
        state=BROKER_RECON_DRY_RUN_PROVEN if proven else BROKER_RECON_DRY_RUN_BLOCKED,
        read_only=True,
        dry_run=bool(_bool(gate.get("dry_run"), default=False) and _bool(receipt.get("dry_run"), default=False)),
        is_order_action=False,
        append=False,
        broker_order_action=False,
        live_order_action=False,
        payload_id=payload_id,
        reconciled_fields=RECONCILED_FIELDS,
        mismatched_fields=tuple(sorted(mismatches)),
        missing_receipt_fields=tuple(sorted(missing)),
        blockers=normalized_blockers,
        warnings=normalized_warnings,
        gate_report=dict(gate),
        broker_receipt=dict(receipt),
        field_comparison=field_comparison,
        metadata={
            "proof": "broker_reconciliation_dry_run_proof_v1",
            "scope": "read_only_no_broker_calls_no_order_submission_no_runtime_wiring",
            "schema_version": BROKER_RECONCILIATION_DRY_RUN_PROOF_SCHEMA_VERSION,
        },
    )


__all__ = [
    "BROKER_RECONCILIATION_DRY_RUN_PROOF_SCHEMA_VERSION",
    "BROKER_RECON_DRY_RUN_BLOCKED",
    "BROKER_RECON_DRY_RUN_PROVEN",
    "BrokerReconciliationDryRunProof",
    "build_broker_reconciliation_dry_run_proof",
]
