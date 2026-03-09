import json
import logging
from pathlib import Path
from datetime import date, datetime
import base64
from core.paths import logs_dir

from config import config as cfg
from core.time_utils import now_ist, now_utc_epoch


def gate_status_path(desk_id: str | None = None) -> Path:
    desk = desk_id or getattr(cfg, "DESK_ID", "DEFAULT")
    return logs_dir() / f"desks/{desk}/gate_status.jsonl"


def gate_status_error_path(desk_id: str | None = None) -> Path:
    desk = desk_id or getattr(cfg, "DESK_ID", "DEFAULT")
    return logs_dir() / f"desks/{desk}/gate_status_errors.jsonl"


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {"encoding": "base64", "data": base64.b64encode(raw).decode("ascii")}
    try:
        module_name = str(getattr(type(value), "__module__", ""))
        if module_name.startswith("numpy"):
            if hasattr(value, "item"):
                return value.item()
            return str(value)
    except Exception:
        pass
    return str(value)


def build_gate_status_record(
    market_data: dict,
    gate_allowed,
    gate_family,
    gate_reasons,
    stage: str,
) -> dict:
    data = market_data or {}
    decision_stage = str(data.get("decision_stage") or "").strip()
    decision_blockers = [str(x) for x in (data.get("decision_blockers") or []) if str(x).strip()]
    effective_stage = decision_stage or stage
    if decision_stage:
        effective_allowed = bool(data.get("decision_allowed", gate_allowed))
        effective_reasons = decision_blockers
    else:
        effective_allowed = bool(gate_allowed)
        effective_reasons = [str(x) for x in (gate_reasons or []) if str(x).strip()]
    regime_probs = data.get("regime_probs") or {}
    max_prob = max(regime_probs.values()) if regime_probs else None
    regime_entropy = data.get("regime_entropy")
    indicator_stale_sec = float(getattr(cfg, "INDICATOR_STALE_SEC", 120))
    never_computed_age = float(getattr(cfg, "INDICATORS_NEVER_COMPUTED_AGE_SEC", 1e9))
    age_raw = data.get("indicators_age_sec")
    try:
        indicators_age_sec = float(age_raw)
    except Exception:
        indicators_age_sec = never_computed_age
    indicator_missing_inputs = list(data.get("indicator_missing_inputs") or data.get("missing_inputs") or [])
    if age_raw is None and "never_computed" not in indicator_missing_inputs:
        indicator_missing_inputs.append("never_computed")

    indicator_reasons = list(indicator_missing_inputs)
    if not bool(data.get("indicators_ok", False)) and "indicators_not_ok" not in indicator_reasons:
        indicator_reasons.append("indicators_not_ok")
    if indicators_age_sec > indicator_stale_sec and "indicators_stale" not in indicator_reasons:
        indicator_reasons.append("indicators_stale")
    if data.get("compute_indicators_error") and "compute_indicators_error" not in indicator_reasons:
        indicator_reasons.append("compute_indicators_error")

    system_state = str(data.get("system_state") or "READY").upper()
    warmup_reasons = list(data.get("warmup_reasons") or [])
    if system_state == "WARMUP" and not warmup_reasons:
        warmup_reasons = list(indicator_reasons)
    if system_state != "WARMUP" and warmup_reasons:
        warmup_reasons = []

    regime_reasons = list(data.get("regime_reasons") or data.get("unstable_reasons") or [])
    if not regime_reasons and bool(data.get("unstable_regime_flag", False)):
        regime_reasons.append("legacy_unstable_flag")
    try:
        prob_min = float(getattr(cfg, "REGIME_PROB_MIN", 0.45))
        if max_prob is not None and float(max_prob) < prob_min and "prob_too_low" not in regime_reasons:
            regime_reasons.append("prob_too_low")
    except Exception:
        pass
    try:
        entropy_max = float(getattr(cfg, "REGIME_ENTROPY_MAX", 1.3))
        if regime_entropy is not None and float(regime_entropy) > entropy_max and "entropy_too_high" not in regime_reasons:
            regime_reasons.append("entropy_too_high")
    except Exception:
        pass

    payload = {
        "symbol": data.get("symbol"),
        "stage": effective_stage,
        "cycle_id": data.get("cycle_id"),
        "execution_mode": str(getattr(cfg, "EXECUTION_MODE", "SIM")),
        "kite_use_api": bool(getattr(cfg, "KITE_USE_API", True)),
        "ltp": data.get("ltp"),
        "ltp_source": data.get("ltp_source"),
        "ltp_ts_epoch": data.get("ltp_ts_epoch"),
        "indicators_ok": bool(data.get("indicators_ok", False)),
        "indicators_age_sec": indicators_age_sec,
        "indicator_stale_sec": indicator_stale_sec,
        "indicator_last_update_epoch": data.get("indicator_last_update_epoch"),
        "indicator_inputs_ok": bool(data.get("indicator_inputs_ok", data.get("indicators_ok", False))),
        "indicator_missing_inputs": indicator_missing_inputs,
        # Backward-compatible key retained for existing readers.
        "missing_inputs": indicator_missing_inputs,
        "indicator_reasons": indicator_reasons,
        "ohlc_seeded": bool(data.get("ohlc_seeded", False)),
        "ohlc_seed_reason": data.get("ohlc_seed_reason"),
        "primary_regime": data.get("primary_regime") or data.get("regime"),
        "regime_confidence": data.get("regime_confidence"),
        "regime_probs_max": max_prob,
        # Backward-compatible key retained for existing dashboards.
        "regime_prob_max": max_prob,
        "regime_entropy": regime_entropy,
        "unstable_reasons": list(data.get("unstable_reasons") or []),
        "regime_reasons": regime_reasons,
        "gate_allowed": bool(effective_allowed),
        "gate_family": gate_family,
        "gate_reasons": list(effective_reasons),
        "ohlc_bars_count": data.get("ohlc_bars_count"),
        "ohlc_last_bar_epoch": data.get("ohlc_last_bar_epoch"),
        "compute_indicators_error": data.get("compute_indicators_error"),
        "system_state": system_state,
        "warmup_reasons": warmup_reasons,
        "warmup_min_bars": data.get("warmup_min_bars"),
        "warmup_bars_by_timeframe": data.get("warmup_bars_by_timeframe"),
        "warmup_min_bars_by_timeframe": data.get("warmup_min_bars_by_timeframe"),
        "decision_allowed": data.get("decision_allowed"),
        "decision_stage": data.get("decision_stage"),
        "decision_blockers": list(data.get("decision_blockers") or []),
        "decision_explain": data.get("decision_explain"),
        "feed_health_snapshot": data.get("feed_health_snapshot") or {},
        "node_call_counts": data.get("node_call_counts") or {},
    }
    return payload


def append_gate_status(record: dict, desk_id: str | None = None) -> bool:
    path = gate_status_path(desk_id=desk_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ts_epoch": now_utc_epoch(),
        "ts_ist": now_ist().isoformat(),
        **(record or {}),
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    payload,
                    ensure_ascii=True,
                    default=_json_default,
                    separators=(",", ":"),
                )
                + "\n"
            )
        return True
    except Exception as exc:
        err_path = gate_status_error_path(desk_id=desk_id)
        try:
            err_path.parent.mkdir(parents=True, exist_ok=True)
            err_payload = {
                "ts_epoch": now_utc_epoch(),
                "ts_ist": now_ist().isoformat(),
                "error_type": type(exc).__name__,
                "error": str(exc),
                "desk_id": desk_id or getattr(cfg, "DESK_ID", "DEFAULT"),
                "record": record or {},
            }
            with err_path.open("a", encoding="utf-8") as ef:
                ef.write(
                    json.dumps(
                        err_payload,
                        ensure_ascii=True,
                        default=_json_default,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        except Exception:
            pass
        logger.error("gate_status_log_write_failed err=%s:%s", type(exc).__name__, exc)
        return False
logger = logging.getLogger(__name__)
