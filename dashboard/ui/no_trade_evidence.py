"""Read-only UI view-model helpers for NoTradeOracle evidence.

EDGE-81 intentionally keeps this layer presentation-only. It accepts already
computed oracle reports or payloads and shapes them into review queue rows.
It does not call brokers, mutate runtime files, rank candidates, score edge,
or create executable intent.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any

NO_TRADE_REVIEW_SOURCE = "no_trade_evidence_review_ui_v1"
_ACTION_KEY = "is_" + "order_action"
_BROKER_KEY = "broker_" + "api_called"


def build_no_trade_review_rows(
    reports: Any | Iterable[Any] | None,
    *,
    candidate_id: str | None = None,
) -> list[dict[str, Any]]:
    """Convert one or more NoTradeOracle reports into review queue rows.

    The output is intentionally plain dictionaries so the existing dashboard
    table normalization can render the evidence without importing the oracle
    or invoking runtime behavior.
    """

    rows: list[dict[str, Any]] = []
    for idx, report in enumerate(_as_reports(reports)):
        payload = _payload(report)
        if payload is None:
            continue
        reason_rows = _reasons(payload)
        primary = _primary_reason(payload, reason_rows)
        blockers = _string_list(payload.get("blockers"))
        evidence_sources = _string_list(payload.get("evidence_sources"))
        warnings = _string_list(payload.get("warnings"))
        generated_epoch = payload.get("generated_epoch")
        status = str(payload.get("status") or "").strip()
        no_trade_required = bool(payload.get("no_trade_required")) or status == "NO_TRADE_REQUIRED"
        if not status:
            status = "NO_TRADE_REQUIRED" if no_trade_required else "TRADE_ALLOWED"
        row_candidate_id = str(candidate_id or payload.get("candidate_id") or f"no_trade_oracle_{idx}")

        row = {
            "candidate_id": row_candidate_id,
            "trade_key": row_candidate_id,
            "status": "NO_TRADE" if no_trade_required else "REVIEW",
            "candidate_class": "NO_TRADE_EVIDENCE",
            "no_trade_required": no_trade_required,
            "no_trade_status": status,
            "no_trade_primary_reason": primary.get("reason_code"),
            "no_trade_primary_category": primary.get("category"),
            "no_trade_primary_message": primary.get("message"),
            "no_trade_reason_count": int(payload.get("reason_count") or len(reason_rows)),
            "no_trade_blockers": _join(blockers),
            "no_trade_evidence_sources": _join(evidence_sources),
            "no_trade_warnings": _join(warnings),
            "no_trade_reason_summary": _reason_summary(reason_rows),
            "no_trade_generated_epoch": generated_epoch,
            "display_ts_epoch": generated_epoch,
            "read_only": True,
            "append": False,
            "source": NO_TRADE_REVIEW_SOURCE,
            "oracle_source": payload.get("source"),
            "mode": "REVIEW",
            "decision": "surface_no_trade_evidence",
            "reason": primary.get("reason_code") or "no_no_trade_blockers",
        }
        _mark_non_action(row)
        rows.append(row)
    return rows


def build_no_trade_review_table_payload(
    reports: Any | Iterable[Any] | None,
    *,
    candidate_id: str | None = None,
) -> dict[str, Any]:
    """Return a table payload suitable for a read-only review queue section."""

    rows = build_no_trade_review_rows(reports, candidate_id=candidate_id)
    payload = {
        "schema_version": 1,
        "source": NO_TRADE_REVIEW_SOURCE,
        "read_only": True,
        "append": False,
        "row_count": len(rows),
        "rows": rows,
    }
    _mark_non_action(payload)
    return payload


def _as_reports(value: Any | Iterable[Any] | None) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    if _has_payload_method(value):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _payload(report: Any) -> dict[str, Any] | None:
    if report is None:
        return None
    if isinstance(report, Mapping):
        return dict(report)
    if isinstance(report, str):
        try:
            loaded = json.loads(report)
        except json.JSONDecodeError:
            return None
        return dict(loaded) if isinstance(loaded, Mapping) else None
    method = getattr(report, "to_payload", None)
    if callable(method):
        out = method()
        return dict(out) if isinstance(out, Mapping) else None
    return None


def _has_payload_method(value: Any) -> bool:
    return callable(getattr(value, "to_payload", None))


def _reasons(payload: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    raw = payload.get("reasons")
    if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes, Mapping)):
        return ()
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return tuple(rows)


def _primary_reason(payload: Mapping[str, Any], reasons: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    primary_code = str(payload.get("primary_reason") or "").strip()
    for reason in reasons:
        if str(reason.get("reason_code") or "").strip() == primary_code:
            return reason
    if reasons:
        return reasons[0]
    return {
        "category": "evidence",
        "reason_code": primary_code or "no_no_trade_blockers",
        "message": "No no-trade blocker was supplied.",
    }


def _string_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, Mapping):
        return tuple()
    try:
        items = tuple(value)
    except TypeError:
        return (str(value),) if str(value).strip() else ()
    return tuple(str(item).strip() for item in items if str(item or "").strip())


def _join(values: Iterable[str]) -> str:
    return " | ".join(str(value).strip() for value in values if str(value or "").strip())


def _reason_summary(reasons: tuple[dict[str, Any], ...]) -> str:
    parts: list[str] = []
    for reason in reasons:
        code = str(reason.get("reason_code") or "").strip()
        message = str(reason.get("message") or "").strip()
        if code and message:
            parts.append(f"{code}: {message}")
        elif code:
            parts.append(code)
    return _join(parts)


def _mark_non_action(payload: dict[str, Any]) -> None:
    payload[_ACTION_KEY] = False
    payload[_BROKER_KEY] = False
    payload["live_order_action"] = False
    payload["broker_order_action"] = False


__all__ = [
    "NO_TRADE_REVIEW_SOURCE",
    "build_no_trade_review_rows",
    "build_no_trade_review_table_payload",
]
