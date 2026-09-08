from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.paths import logs_dir


CANONICAL_ROW_KIND = "canonical_suggestion"
BLOCKED_DEBUG_ROW_KIND = "blocked_debug"
ADVISORY_ONLY_ROW_KIND = "advisory_only"


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _is_option_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    instrument_type = str(row.get("instrument_type") or row.get("instrument") or "").strip().upper()
    if instrument_type in {"OPT", "OPTION", "OPTIONS", "OPTIDX", "OPTSTK", "CE", "PE"}:
        return True
    option_type = str(row.get("option_type") or row.get("type") or row.get("right") or "").strip().upper()
    if option_type in {"CE", "PE", "CALL", "PUT"}:
        return True
    return False


def _option_bid_ask_spread(row: dict[str, Any]) -> float | None:
    bid = _safe_float(row.get("best_bid"))
    if bid is None:
        bid = _safe_float(row.get("bid"))
    if bid is None:
        bid = _safe_float(row.get("opt_bid"))
    ask = _safe_float(row.get("best_ask"))
    if ask is None:
        ask = _safe_float(row.get("ask"))
    if ask is None:
        ask = _safe_float(row.get("opt_ask"))
    if bid is None or ask is None:
        return None
    spread = ask - bid
    if spread <= 0:
        return None
    return spread


def advisory_row_corruption_log_path() -> Path:
    return logs_dir() / "advisory_row_corruption.jsonl"


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    from core.log_writer import get_jsonl_writer
    if not get_jsonl_writer(path).write(payload):
        raise OSError("bounded_advisory_corruption_write_rejected")


def log_corrupt_advisory_row(row: dict[str, Any], reason: str) -> None:
    payload = row if isinstance(row, dict) else {}
    _append_jsonl(
        advisory_row_corruption_log_path(),
        {
            "ts_epoch": datetime.now(timezone.utc).timestamp(),
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "reason": str(reason or "unknown"),
            "trade_id": payload.get("trade_id"),
            "symbol": payload.get("symbol"),
            "row_kind": payload.get("row_kind"),
            "entry": payload.get("entry"),
            "final_entry": payload.get("final_entry"),
            "stop_loss": payload.get("stop_loss", payload.get("stop")),
            "target": payload.get("target"),
            "entry_source": payload.get("entry_source"),
            "execution_entry_source": payload.get("execution_entry_source"),
            "display_entry_source": payload.get("display_entry_source"),
        },
    )


def _set_stop_fields(row: dict[str, Any], stop_value: float | None) -> None:
    row["stop"] = stop_value
    row["stop_loss"] = stop_value
    row["stop_price"] = stop_value
    row["original_stop"] = stop_value
    row["current_stop"] = stop_value


def _set_target_fields(row: dict[str, Any], target_value: float | None) -> None:
    row["target"] = target_value
    row["target_price"] = target_value


def recompute_levels_from_final_entry(
    row: dict[str, Any],
    *,
    rr_default: float = 1.5,
    option_stop_tighten: bool = False,
    option_stop_max_pct: float | None = None,
    option_stop_min_pct: float | None = None,
    option_stop_spread_mult: float | None = None,
    option_stop_max_abs: float | None = None,
    option_stop_min_abs: float | None = None,
) -> dict[str, Any]:
    out = dict(row) if isinstance(row, dict) else {}
    final_entry = _safe_float(out.get("final_entry"))
    side = str(out.get("side") or "BUY").strip().upper() or "BUY"

    if final_entry is None:
        _set_stop_fields(out, None)
        _set_target_fields(out, None)
        out["non_canonical_levels"] = True
        out["levels_recomputed_from_final_entry"] = False
        out["level_recompute_reason"] = "missing_final_entry"
        return out

    risk = _safe_float(out.get("capital_at_risk"))
    if risk is None or risk <= 0.0:
        old_stop = _safe_float(out.get("stop_loss"))
        if old_stop is None:
            old_stop = _safe_float(out.get("stop"))
        if old_stop is not None:
            risk = abs(final_entry - old_stop)

    if option_stop_tighten and _is_option_row(out) and side == "BUY":
        spread = _option_bid_ask_spread(out)
        spread_floor = None
        if spread is not None and option_stop_spread_mult is not None and option_stop_spread_mult > 0:
            spread_floor = spread * option_stop_spread_mult
        max_risk = None
        if option_stop_max_pct is not None and option_stop_max_pct > 0:
            max_risk = final_entry * option_stop_max_pct
        min_risk = None
        if option_stop_min_pct is not None and option_stop_min_pct > 0:
            min_risk = final_entry * option_stop_min_pct
        candidate_risk = risk
        if candidate_risk is None or candidate_risk <= 0.0:
            candidate_risk = 0.0
        if min_risk is not None:
            candidate_risk = max(candidate_risk, min_risk)
        if option_stop_min_abs is not None and option_stop_min_abs > 0:
            candidate_risk = max(candidate_risk, option_stop_min_abs)
        if spread_floor is not None:
            candidate_risk = max(candidate_risk, spread_floor)
        if max_risk is not None:
            candidate_risk = min(candidate_risk, max_risk)
        if option_stop_max_abs is not None and option_stop_max_abs > 0:
            candidate_risk = min(candidate_risk, option_stop_max_abs)
        candidate_risk = min(candidate_risk, final_entry * 0.99)
        if candidate_risk > 0.0:
            risk = candidate_risk

    if risk is None or risk <= 0.0:
        _set_stop_fields(out, None)
        _set_target_fields(out, None)
        out["non_canonical_levels"] = True
        out["levels_recomputed_from_final_entry"] = False
        out["level_recompute_reason"] = "insufficient_risk_context"
        return out

    rr = _safe_float(out.get("rr_ratio"))
    if rr is None or rr <= 0.0:
        rr = _safe_float(out.get("target_rr"))
    if rr is None or rr <= 0.0:
        rr = float(rr_default)

    if side == "SELL":
        stop_value = round(final_entry + risk, 2)
        target_value = round(final_entry - (risk * rr), 2)
    else:
        stop_value = round(final_entry - risk, 2)
        target_value = round(final_entry + (risk * rr), 2)

    _set_stop_fields(out, stop_value)
    _set_target_fields(out, target_value)
    out["capital_at_risk"] = round(risk, 2)
    out["target_rr"] = rr
    out["levels_recomputed_from_final_entry"] = True
    out["non_canonical_levels"] = False
    out["level_recompute_reason"] = None
    return out


def validate_price_level_invariants(payload: dict[str, Any]) -> str | None:
    if not isinstance(payload, dict):
        return "row_not_object"
    row_kind = str(payload.get("row_kind") or ADVISORY_ONLY_ROW_KIND).strip().lower()
    if row_kind != CANONICAL_ROW_KIND:
        return None

    side = str(payload.get("side") or "BUY").strip().upper() or "BUY"
    entry = _safe_float(payload.get("entry"))
    stop_loss = _safe_float(payload.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _safe_float(payload.get("stop"))
    target = _safe_float(payload.get("target"))

    if entry is None or stop_loss is None or target is None:
        return "canonical_suggestion requires entry/stop_loss/target"

    if side == "SELL":
        if not (target < entry < stop_loss):
            return "SELL invariant failed: target < entry < stop_loss"
        return None

    if not (stop_loss < entry < target):
        return "BUY invariant failed: stop_loss < entry < target"
    return None
