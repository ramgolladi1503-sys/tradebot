from __future__ import annotations

from typing import Any, Mapping

from .contracts import AgentEvidenceRef


def evidence_ref_from_mapping(source_path: str, payload: Mapping[str, Any], *, line_number: int | None = None) -> AgentEvidenceRef:
    return AgentEvidenceRef(
        source_path=source_path,
        line_number=line_number,
        event=str(payload.get("event") or payload.get("event_type") or "").strip() or None,
        ts_epoch=_safe_float(payload.get("ts_epoch") or payload.get("timestamp_epoch") or payload.get("generated_epoch")),
        ts_ist=str(payload.get("ts_ist") or payload.get("timestamp") or "").strip() or None,
        excerpt=_short_excerpt(payload),
        fields={key: value for key, value in payload.items() if key not in {"event", "event_type", "ts_epoch", "timestamp_epoch", "generated_epoch", "ts_ist", "timestamp"}},
    )


def evidence_ref_from_text(source_path: str, excerpt: str, *, line_number: int | None = None, event: str | None = None) -> AgentEvidenceRef:
    return AgentEvidenceRef(
        source_path=source_path,
        line_number=line_number,
        event=event,
        excerpt=excerpt.strip(),
        fields={},
    )


def _short_excerpt(payload: Mapping[str, Any]) -> str:
    for key in ("message", "reason", "summary", "event", "event_type"):
        value = payload.get(key)
        if value not in (None, "", [], {}, ()):
            return str(value).strip()
    return ""


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None
