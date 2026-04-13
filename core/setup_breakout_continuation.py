from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import config as cfg


@dataclass(frozen=True)
class BreakoutContinuationSetupResult:
    detected: bool
    direction: str
    setup_score: float
    trigger_score: float
    entry_quality_score: float
    rr: float
    entry: float
    stop: float
    target: float
    telemetry: dict[str, Any]


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "", "None"):
            return None
        return float(value)
    except Exception:
        return None


def _candidate_get(candidate: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in candidate and candidate.get(key) is not None:
            return candidate.get(key)
    return None


def _normalize_direction(raw_value: Any) -> str:
    text = str(raw_value or "").strip().upper()
    if text in {"BUY_CALL", "CALL", "CE", "LONG_CALL", "BUY"}:
        return "BUY_CALL"
    if text in {"BUY_PUT", "PUT", "PE", "LONG_PUT"}:
        return "BUY_PUT"
    if "PUT" in text or text.endswith("PE"):
        return "BUY_PUT"
    return "BUY_CALL"


def _breakout_detection(candidate: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    telemetry: dict[str, Any] = {}
    source_flags = candidate.get("source_flags")
    if not isinstance(source_flags, dict):
        source_flags = {}

    explicit_detected = bool(candidate.get("breakout_detected")) or bool(
        source_flags.get("breakout_detected")
    )
    strategy_family = str(candidate.get("strategy_family") or "").strip().lower()
    setup_name = str(candidate.get("setup_name") or "").strip().lower()
    decision_playbook = str(candidate.get("decision_playbook") or "").strip().lower()
    hinted = (
        strategy_family == "breakout_continuation"
        or setup_name == "trend_breakout_continuation"
        or decision_playbook == "breakout_continuation"
        or explicit_detected
    )
    if hinted:
        direction = _normalize_direction(
            _candidate_get(candidate, "setup_direction", "direction", "side", "option_type", "right")
        )
        telemetry["detection_source"] = "explicit_breakout_identity"
        telemetry["direction"] = direction
        return True, direction, telemetry

    entry = _safe_float(
        _candidate_get(candidate, "execution_entry", "display_entry", "entry", "opt_ltp", "current_ltp", "ltp")
    )
    day_high = _safe_float(
        _candidate_get(candidate, "day_high", "session_high", "high_of_day", "intraday_high")
    )
    day_low = _safe_float(
        _candidate_get(candidate, "day_low", "session_low", "low_of_day", "intraday_low")
    )
    bar_open = _safe_float(_candidate_get(candidate, "candle_open", "bar_open", "open"))
    bar_close = _safe_float(_candidate_get(candidate, "candle_close", "bar_close", "close", "current_ltp"))
    min_body = float(getattr(cfg, "PHASE2_BREAKOUT_MIN_BODY_PCT", 0.003) or 0.003)
    buffer_pct = float(getattr(cfg, "PHASE2_BREAKOUT_BUFFER_PCT", 0.001) or 0.001)

    bullish_body = 0.0
    bearish_body = 0.0
    if bar_open is not None and bar_close is not None:
        bullish_body = max(0.0, bar_close - bar_open) / max(abs(bar_open), 1e-9)
        bearish_body = max(0.0, bar_open - bar_close) / max(abs(bar_open), 1e-9)
    bullish_strength = bullish_body >= min_body
    bearish_strength = bearish_body >= min_body

    up_breakout = (
        entry is not None
        and day_high is not None
        and entry > (day_high * (1.0 + buffer_pct))
        and bullish_strength
    )
    down_breakout = (
        entry is not None
        and day_low is not None
        and entry < (day_low * (1.0 - buffer_pct))
        and bearish_strength
    )

    telemetry.update(
        {
            "entry": entry,
            "day_high": day_high,
            "day_low": day_low,
            "bar_open": bar_open,
            "bar_close": bar_close,
            "bullish_body": bullish_body,
            "bearish_body": bearish_body,
            "min_body_pct": min_body,
            "buffer_pct": buffer_pct,
            "up_breakout": up_breakout,
            "down_breakout": down_breakout,
        }
    )

    if up_breakout:
        telemetry["detection_source"] = "price_action_up_breakout"
        return True, "BUY_CALL", telemetry
    if down_breakout:
        telemetry["detection_source"] = "price_action_down_breakout"
        return True, "BUY_PUT", telemetry

    telemetry["detection_source"] = "none"
    return False, "BUY_CALL", telemetry


def _entry_levels(
    candidate: dict[str, Any], *, direction: str
) -> tuple[float | None, float | None, float | None]:
    entry = _safe_float(
        _candidate_get(candidate, "execution_entry", "display_entry", "entry", "opt_ltp", "current_ltp", "ltp")
    )
    stop = _safe_float(_candidate_get(candidate, "stop_loss", "stop", "stop_price"))
    target = _safe_float(_candidate_get(candidate, "target", "target_price"))

    if entry is None or entry <= 0:
        return None, stop, target

    buy_stop_mult = float(getattr(cfg, "PHASE2_BREAKOUT_BUY_STOP_MULT", 0.88) or 0.88)
    buy_target_mult = float(getattr(cfg, "PHASE2_BREAKOUT_BUY_TARGET_MULT", 1.24) or 1.24)
    sell_stop_mult = float(getattr(cfg, "PHASE2_BREAKOUT_SELL_STOP_MULT", 1.12) or 1.12)
    sell_target_mult = float(getattr(cfg, "PHASE2_BREAKOUT_SELL_TARGET_MULT", 0.76) or 0.76)

    if direction == "BUY_PUT":
        stop = stop if stop is not None else round(entry * sell_stop_mult, 3)
        target = target if target is not None else round(entry * sell_target_mult, 3)
    else:
        stop = stop if stop is not None else round(entry * buy_stop_mult, 3)
        target = target if target is not None else round(entry * buy_target_mult, 3)
    return entry, stop, target


def _rr(entry: float, stop: float, target: float) -> float:
    reward = abs(float(target) - float(entry))
    risk = max(abs(float(entry) - float(stop)), 1e-6)
    return float(reward / risk)


def evaluate_breakout_continuation_setup(candidate: dict[str, Any]) -> BreakoutContinuationSetupResult:
    if not isinstance(candidate, dict):
        return BreakoutContinuationSetupResult(
            detected=False,
            direction="BUY_CALL",
            setup_score=0.0,
            trigger_score=0.0,
            entry_quality_score=0.0,
            rr=0.0,
            entry=0.0,
            stop=0.0,
            target=0.0,
            telemetry={"detection_source": "invalid_candidate"},
        )

    detected, direction, telemetry = _breakout_detection(candidate)
    entry, stop, target = _entry_levels(candidate, direction=direction)
    if not detected or entry is None or stop is None or target is None:
        telemetry["detected"] = False
        telemetry["has_entry"] = bool(entry is not None)
        telemetry["has_stop"] = bool(stop is not None)
        telemetry["has_target"] = bool(target is not None)
        return BreakoutContinuationSetupResult(
            detected=False,
            direction=direction,
            setup_score=0.0,
            trigger_score=0.0,
            entry_quality_score=0.0,
            rr=0.0,
            entry=float(entry or 0.0),
            stop=float(stop or 0.0),
            target=float(target or 0.0),
            telemetry=telemetry,
        )

    setup_score = max(
        float(_safe_float(candidate.get("setup_score")) or 0.0),
        float(_safe_float(candidate.get("breakout_setup_score")) or getattr(cfg, "PHASE2_BREAKOUT_SETUP_SCORE_DEFAULT", 0.70)),
    )
    trigger_score = max(
        float(_safe_float(candidate.get("trigger_score")) or 0.0),
        float(_safe_float(candidate.get("breakout_trigger_score")) or getattr(cfg, "PHASE2_BREAKOUT_TRIGGER_SCORE_DEFAULT", 0.68)),
    )
    entry_quality_score = max(
        float(_safe_float(candidate.get("entry_quality_score")) or 0.0),
        float(
            _safe_float(candidate.get("breakout_entry_quality_score"))
            or getattr(cfg, "PHASE2_BREAKOUT_ENTRY_QUALITY_SCORE_DEFAULT", 0.66)
        ),
    )
    rr_value = _rr(entry, stop, target)
    telemetry.update(
        {
            "detected": True,
            "direction": direction,
            "entry": entry,
            "stop": stop,
            "target": target,
            "rr": rr_value,
        }
    )
    return BreakoutContinuationSetupResult(
        detected=True,
        direction=direction,
        setup_score=float(setup_score),
        trigger_score=float(trigger_score),
        entry_quality_score=float(entry_quality_score),
        rr=float(rr_value),
        entry=float(entry),
        stop=float(stop),
        target=float(target),
        telemetry=telemetry,
    )

