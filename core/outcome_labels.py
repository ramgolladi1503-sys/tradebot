from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from config import config as cfg


OUTCOME_LABEL_SCHEMA_VERSION = 1

SUPPORTED_OUTCOME_LABELS = {
    "favorable_excursion",
    "adverse_excursion",
    "blocked_correctly",
    "blocked_falsely",
    "skipped_by_allocator",
    "non_executable_then_executable_later",
    "poor_fill_quality",
    "thesis_invalidated_quickly",
    "advisory_only_never_became_executable",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _coerce_epoch(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        raw = float(value)
        if raw <= 0:
            return None
        if raw > 1_000_000_000_000:
            return raw / 1000.0
        return raw
    text = _text(value)
    if not text:
        return None
    try:
        return _coerce_epoch(float(text))
    except Exception:
        pass
    try:
        normalized = text.replace("Z", "+00:00") if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.timestamp()
    except Exception:
        return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = _text(value).lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return bool(value)


def _candidate_not_executed(row: Mapping[str, Any]) -> bool:
    allocation_reason = _text(row.get("allocation_reason")).lower()
    if allocation_reason.startswith("deferred_") or allocation_reason.startswith("replaced_"):
        return True
    permission = _text(row.get("permission")).upper()
    readiness = _text(row.get("readiness")).upper()
    execution_status = _text(row.get("execution_status")).lower()
    status = _text(row.get("status")).upper()
    if permission in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCK"}:
        return True
    if readiness in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCKED"}:
        return True
    if execution_status in {"advisory_only", "queue_only", "blocked", "non_executable"}:
        return True
    if status in {"ADVISORY_ONLY", "QUEUE_ONLY", "BLOCKED", "INVALID"}:
        return True
    return False


def _normalize_candidate_outcome(value: Any) -> str:
    text = _text(value).lower()
    mapping = {
        "target": "target",
        "target_hit": "target",
        "hit_target": "target",
        "win": "target",
        "stop": "stop",
        "stop_hit": "stop",
        "hit_sl": "stop",
        "loss": "stop",
        "no_hit": "no_hit",
        "": "no_hit",
    }
    return mapping.get(text, text or "no_hit")


def _provenance(scope: str, label: str, rule: str, *, evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
    clean_evidence = {}
    for key, value in dict(evidence or {}).items():
        if value in (None, "", [], {}):
            continue
        clean_evidence[str(key)] = value
    return {
        "version": OUTCOME_LABEL_SCHEMA_VERSION,
        "scope": str(scope),
        "rule": str(rule),
        "label": str(label),
        "evidence": clean_evidence,
    }


def classify_candidate_outcome(row: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    allocation_reason = _text(row.get("allocation_reason")).lower()
    if allocation_reason.startswith("deferred_") or allocation_reason.startswith("replaced_"):
        label = "skipped_by_allocator"
        return label, _provenance(
            "candidate",
            label,
            "allocation_reason",
            evidence={"allocation_reason": allocation_reason},
        )

    execution_status = _text(row.get("execution_status")).lower()
    later_execution_status = _text(row.get("later_execution_status")).lower()
    became_executable_later = _bool(row.get("became_executable_later")) or later_execution_status == "executable"
    if execution_status in {"advisory_only", "queue_only", "blocked", "non_executable"} and became_executable_later:
        label = "non_executable_then_executable_later"
        return label, _provenance(
            "candidate",
            label,
            "execution_transition",
            evidence={
                "execution_status": execution_status,
                "later_execution_status": later_execution_status or "executable",
            },
        )

    outcome = _normalize_candidate_outcome(row.get("outcome") or row.get("outcome_label"))
    not_executed = _candidate_not_executed(row)
    if not_executed and outcome == "target":
        label = "blocked_falsely"
        return label, _provenance(
            "candidate",
            label,
            "blocked_then_target",
            evidence={
                "outcome": outcome,
                "permission": _text(row.get("permission")).upper() or None,
                "execution_status": execution_status or None,
            },
        )
    if not_executed and outcome == "stop":
        label = "blocked_correctly"
        return label, _provenance(
            "candidate",
            label,
            "blocked_then_stop",
            evidence={
                "outcome": outcome,
                "permission": _text(row.get("permission")).upper() or None,
                "execution_status": execution_status or None,
            },
        )
    if not_executed and outcome == "no_hit":
        label = "advisory_only_never_became_executable"
        return label, _provenance(
            "candidate",
            label,
            "non_executable_no_terminal_outcome",
            evidence={
                "permission": _text(row.get("permission")).upper() or None,
                "readiness": _text(row.get("readiness")).upper() or None,
                "execution_status": execution_status or None,
            },
        )

    mfe = _safe_float(row.get("mfe"))
    mae = _safe_float(row.get("mae"))
    pnl = _safe_float(row.get("pnl")) or _safe_float(row.get("realized_pnl"))
    entry = _safe_float(row.get("entry")) or _safe_float(row.get("entry_price"))
    ltp = _safe_float(row.get("ltp")) or _safe_float(row.get("exit"))
    if pnl is None and entry is not None and ltp is not None:
        side = _text(row.get("side") or "BUY").upper()
        direction = -1.0 if side in {"SELL", "SHORT"} else 1.0
        pnl = (float(ltp) - float(entry)) * direction

    if outcome == "target" or (mfe is not None and mfe > 0 and (mae is None or abs(mfe) >= abs(mae))) or (pnl is not None and pnl > 0):
        label = "favorable_excursion"
        return label, _provenance(
            "candidate",
            label,
            "favorable_path",
            evidence={"outcome": outcome, "mfe": mfe, "pnl": pnl},
        )

    label = "adverse_excursion"
    return label, _provenance(
        "candidate",
        label,
        "adverse_path",
        evidence={"outcome": outcome, "mae": mae, "pnl": pnl},
    )


def attach_candidate_outcome_labels(row: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(row or {})
    label, provenance = classify_candidate_outcome(out)
    out["candidate_outcome_label"] = label
    out["candidate_outcome_label_provenance"] = provenance
    return out


def _trade_duration_sec(row: Mapping[str, Any]) -> float | None:
    opened = _coerce_epoch(row.get("timestamp")) or _coerce_epoch(row.get("entry_time"))
    closed = _coerce_epoch(row.get("exit_time"))
    if opened is None or closed is None or closed < opened:
        return None
    return float(closed - opened)


def classify_trade_outcome(row: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    entry = _safe_float(row.get("entry")) or _safe_float(row.get("entry_price"))
    reference = _safe_float(row.get("fill_price"))
    if reference is None:
        reference = _safe_float(row.get("expected_entry")) or _safe_float(row.get("execution_entry")) or entry
    stop = _safe_float(row.get("stop_loss")) or _safe_float(row.get("stop"))
    exit_price = _safe_float(row.get("exit_price")) or _safe_float(row.get("exit"))
    realized_pnl = _safe_float(row.get("realized_pnl"))
    if realized_pnl is None and entry is not None and exit_price is not None:
        side = _text(row.get("side") or "BUY").upper()
        direction = -1.0 if side in {"SELL", "SHORT"} else 1.0
        qty_units = _safe_float(row.get("qty_units")) or _safe_float(row.get("qty")) or 1.0
        realized_pnl = (float(exit_price) - float(entry)) * direction * float(qty_units)

    side = _text(row.get("side") or "BUY").upper()
    slippage = _safe_float(row.get("slippage"))
    adverse_fill = None
    if reference is not None and entry is not None:
        adverse_fill = float(reference) - float(entry) if side not in {"SELL", "SHORT"} else float(entry) - float(reference)
    initial_risk = None
    if reference is not None and stop is not None:
        initial_risk = abs(float(reference) - float(stop))

    poor_fill_fraction = float(getattr(cfg, "OUTCOME_LABEL_POOR_FILL_QUALITY_RISK_FRACTION", 0.5))
    if adverse_fill is not None and adverse_fill > 0:
        fill_ratio = (adverse_fill / initial_risk) if initial_risk not in (None, 0.0) else None
        if (slippage is not None and slippage > 0) or (fill_ratio is not None and fill_ratio >= poor_fill_fraction):
            label = "poor_fill_quality"
            return label, _provenance(
                "trade",
                label,
                "adverse_fill_vs_reference",
                evidence={
                    "entry": entry,
                    "fill_price": reference,
                    "slippage": slippage,
                    "adverse_fill": round(float(adverse_fill), 6),
                    "fill_risk_fraction": round(float(fill_ratio), 6) if fill_ratio is not None else None,
                },
            )

    exit_reason = _text(row.get("exit_reason")).upper()
    duration_sec = _trade_duration_sec(row)
    quick_seconds = float(getattr(cfg, "OUTCOME_LABEL_THESIS_INVALIDATED_SECONDS", 900))
    negative_or_flat = realized_pnl is None or realized_pnl <= 0
    if negative_or_flat and duration_sec is not None and duration_sec <= quick_seconds and exit_reason in {"STOP", "STOP_HIT", "SL", "TRAIL_STOP", "THESIS_INVALIDATED"}:
        label = "thesis_invalidated_quickly"
        return label, _provenance(
            "trade",
            label,
            "fast_negative_exit",
            evidence={
                "exit_reason": exit_reason,
                "duration_sec": round(float(duration_sec), 3),
                "realized_pnl": realized_pnl,
            },
        )

    if realized_pnl is not None and realized_pnl > 0:
        label = "favorable_excursion"
        return label, _provenance(
            "trade",
            label,
            "positive_realized_pnl",
            evidence={"realized_pnl": realized_pnl, "exit_reason": exit_reason or None},
        )

    label = "adverse_excursion"
    return label, _provenance(
        "trade",
        label,
        "non_positive_realized_pnl",
        evidence={"realized_pnl": realized_pnl, "exit_reason": exit_reason or None},
    )


def attach_trade_outcome_labels(row: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(row or {})
    label, provenance = classify_trade_outcome(out)
    out["trade_outcome_label"] = label
    out["trade_outcome_label_provenance"] = provenance
    return out
