from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ExitAction(str, Enum):
    NOOP = "NOOP"
    MODIFY_PLAN = "MODIFY_PLAN"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    FULL_EXIT = "FULL_EXIT"


@dataclass(frozen=True)
class ExitDecision:
    action: ExitAction
    reason_codes: tuple[str, ...]
    before_plan: dict[str, Any]
    after_plan: dict[str, Any]
    state_patch: dict[str, Any] = field(default_factory=dict)
    exit_qty_units: int = 0
    safe_mode: bool = False
    cooldown_applied: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason_codes": list(self.reason_codes),
            "before_plan": dict(self.before_plan),
            "after_plan": dict(self.after_plan),
            "state_patch": dict(self.state_patch),
            "exit_qty_units": int(self.exit_qty_units),
            "safe_mode": bool(self.safe_mode),
            "cooldown_applied": bool(self.cooldown_applied),
        }


def _to_float(value: Any) -> float | None:
    try:
        out = float(value)
        if out != out:  # NaN guard
            return None
        return out
    except Exception:
        return None


def _better_price(side: str, current: float, baseline: float) -> bool:
    return current >= baseline if side == "BUY" else current <= baseline


def _tighten_stop(side: str, current_sl: float, candidate_sl: float) -> float:
    if side == "BUY":
        return max(current_sl, candidate_sl)
    return min(current_sl, candidate_sl)


def _profit_progress(side: str, entry: float, target: float, current: float) -> float | None:
    denom = (target - entry) if side == "BUY" else (entry - target)
    if denom <= 0:
        return None
    numer = (current - entry) if side == "BUY" else (entry - current)
    return numer / denom


def _derive_safe_mode(
    market_snapshot: Mapping[str, Any],
    *,
    allow_stale_quotes: bool,
    max_quote_age_sec: float,
) -> tuple[bool, str | None]:
    feed_state = str(market_snapshot.get("feed_state") or "").upper()
    quote_age = _to_float(
        market_snapshot.get("option_age_sec")
        or market_snapshot.get("quote_age_sec")
        or market_snapshot.get("price_age_sec")
    )
    if feed_state in {"DEGRADED", "DOWN", "UNKNOWN"}:
        return True, f"feed_{feed_state.lower()}"
    if quote_age is not None and (quote_age > max_quote_age_sec) and (not allow_stale_quotes):
        return True, "quote_stale"
    return False, None


def evaluate_exit(position: Mapping[str, Any], market_snapshot: Mapping[str, Any], now_ts: float, cfg: Any) -> ExitDecision:
    """
    Deterministic exit policy evaluator.
    Inputs are treated as immutable snapshots and all decisions are derived from them.
    """
    side = str(position.get("side") or "BUY").upper()
    if side not in {"BUY", "SELL"}:
        side = "BUY"

    entry = _to_float(position.get("entry_price"))
    current_sl = _to_float(position.get("current_sl"))
    current_tp = _to_float(position.get("current_tp"))
    current_price = _to_float(
        market_snapshot.get("ltp")
        or market_snapshot.get("mark_price")
        or market_snapshot.get("last_price")
        or position.get("last_price")
    )
    qty_units = max(0, int(position.get("remaining_qty_units") or position.get("qty_units") or position.get("qty") or 0))
    best_price_seen = _to_float(position.get("best_price_seen"))
    best_price_ts = _to_float(position.get("best_price_ts"))
    last_action_ts = _to_float(position.get("last_action_ts")) or 0.0
    stall_counter = max(0, int(position.get("stall_counter") or 0))
    phase = str(position.get("exit_intel_phase") or "INIT").upper()
    entry_time = _to_float(position.get("entry_time")) or now_ts
    elapsed_sec = max(0.0, float(now_ts) - float(entry_time))

    before_plan = {
        "current_sl": current_sl,
        "current_tp": current_tp,
        "best_price_seen": best_price_seen,
        "best_price_ts": best_price_ts,
        "exit_intel_phase": phase,
        "stall_counter": stall_counter,
        "last_action_ts": last_action_ts,
    }
    if entry is None or current_sl is None or current_tp is None or current_price is None or qty_units <= 0:
        return ExitDecision(
            action=ExitAction.NOOP,
            reason_codes=("missing_exit_inputs",),
            before_plan=before_plan,
            after_plan=dict(before_plan),
            state_patch={},
            exit_qty_units=0,
        )

    allow_stale_quotes = bool(getattr(cfg, "ALLOW_STALE_LTP", False))
    max_quote_age_sec = float(getattr(cfg, "EXIT_INTEL_MAX_QUOTE_AGE_SEC", 2.5))
    safe_mode, safe_reason = _derive_safe_mode(
        market_snapshot,
        allow_stale_quotes=allow_stale_quotes,
        max_quote_age_sec=max_quote_age_sec,
    )

    updated_best = best_price_seen if best_price_seen is not None else entry
    updated_best_ts = best_price_ts if best_price_ts is not None else now_ts
    made_new_best = _better_price(side, current_price, updated_best)
    if made_new_best:
        updated_best = current_price
        updated_best_ts = now_ts
        stall_counter_next = 0
    else:
        stall_counter_next = stall_counter + 1

    updated_phase = phase
    state_patch: dict[str, Any] = {
        "best_price_seen": updated_best,
        "best_price_ts": updated_best_ts,
        "stall_counter": stall_counter_next,
        "exit_intel_phase": updated_phase,
        "reason_codes": [],
    }

    # Hard exits: always allowed even in safe mode.
    hit_target = _better_price(side, current_price, current_tp)
    hit_stop = not _better_price(side, current_price, current_sl)
    max_hold_sec = float(position.get("max_hold_sec") or getattr(cfg, "MAX_HOLD_MINUTES", 60) * 60)
    hit_time = elapsed_sec >= max_hold_sec
    if hit_target or hit_stop or hit_time:
        reason = "TARGET_HIT" if hit_target else ("STOP_HIT" if hit_stop else "TIME_EXIT")
        state_patch.update(
            {
                "exit_intel_phase": "FINAL_EXIT",
                "last_action_ts": now_ts,
                "reason_codes": [reason],
            }
        )
        after_plan = dict(before_plan)
        after_plan.update(state_patch)
        return ExitDecision(
            action=ExitAction.FULL_EXIT,
            reason_codes=(reason,),
            before_plan=before_plan,
            after_plan=after_plan,
            state_patch=state_patch,
            exit_qty_units=qty_units,
            safe_mode=safe_mode,
        )

    cooldown_sec = float(getattr(cfg, "EXIT_INTEL_ACTION_COOLDOWN_SEC", 15.0))
    if (now_ts - last_action_ts) < cooldown_sec:
        state_patch["reason_codes"] = ["cooldown_active"]
        after_plan = dict(before_plan)
        after_plan.update(state_patch)
        return ExitDecision(
            action=ExitAction.NOOP,
            reason_codes=("cooldown_active",),
            before_plan=before_plan,
            after_plan=after_plan,
            state_patch=state_patch,
            cooldown_applied=True,
            safe_mode=safe_mode,
        )

    # Profit protect to break-even+buffer.
    profit_trigger_pct = float(getattr(cfg, "EXIT_INTEL_PROFIT_PROTECT_TRIGGER_PCT", 0.01))
    be_buffer_pct = float(getattr(cfg, "EXIT_INTEL_BREAK_EVEN_BUFFER_PCT", 0.0005))
    be_price = entry * (1.0 + be_buffer_pct if side == "BUY" else 1.0 - be_buffer_pct)
    protect_trigger = entry * (1.0 + profit_trigger_pct if side == "BUY" else 1.0 - profit_trigger_pct)
    protect_ready = _better_price(side, current_price, protect_trigger)
    if protect_ready:
        tightened = _tighten_stop(side, current_sl, be_price)
        if ((side == "BUY" and tightened > current_sl) or (side == "SELL" and tightened < current_sl)):
            updated_phase = "PROTECT"
            state_patch.update(
                {
                    "current_sl": tightened,
                    "exit_intel_phase": updated_phase,
                    "last_action_ts": now_ts,
                    "reason_codes": ["profit_protect_be"],
                }
            )
            after_plan = dict(before_plan)
            after_plan.update(state_patch)
            return ExitDecision(
                action=ExitAction.MODIFY_PLAN,
                reason_codes=("profit_protect_be",),
                before_plan=before_plan,
                after_plan=after_plan,
                state_patch=state_patch,
                safe_mode=safe_mode,
            )

    # Trail stop by best seen price (never widen).
    trail_offset_pct = float(getattr(cfg, "EXIT_INTEL_TRAIL_OFFSET_PCT", 0.005))
    trail_step_pct = float(getattr(cfg, "EXIT_INTEL_TRAIL_STEP_PCT", 0.002))
    atr = _to_float(market_snapshot.get("atr"))
    use_atr = bool(getattr(cfg, "EXIT_INTEL_TRAIL_USE_ATR", True)) and (atr is not None and atr > 0.0)
    atr_mult = float(getattr(cfg, "EXIT_INTEL_TRAIL_ATR_MULT", 0.8))
    if use_atr:
        trail_candidate = (updated_best - atr * atr_mult) if side == "BUY" else (updated_best + atr * atr_mult)
    else:
        trail_candidate = updated_best * (1.0 - trail_offset_pct if side == "BUY" else 1.0 + trail_offset_pct)
    best_delta = abs(updated_best - (best_price_seen if best_price_seen is not None else entry))
    if best_delta >= (abs(entry) * trail_step_pct):
        tightened = _tighten_stop(side, current_sl, trail_candidate)
        if ((side == "BUY" and tightened > current_sl) or (side == "SELL" and tightened < current_sl)):
            updated_phase = "TRAIL"
            state_patch.update(
                {
                    "current_sl": tightened,
                    "exit_intel_phase": updated_phase,
                    "last_action_ts": now_ts,
                    "reason_codes": ["trail_upgrade"],
                }
            )
            after_plan = dict(before_plan)
            after_plan.update(state_patch)
            return ExitDecision(
                action=ExitAction.MODIFY_PLAN,
                reason_codes=("trail_upgrade",),
                before_plan=before_plan,
                after_plan=after_plan,
                state_patch=state_patch,
                safe_mode=safe_mode,
            )

    # Stall near target -> partial/full exit if momentum breaks.
    progress = _profit_progress(side, entry, current_tp, current_price)
    stall_target_pct = float(getattr(cfg, "EXIT_INTEL_STALL_TARGET_PCT", 0.9))
    stall_seconds = float(getattr(cfg, "EXIT_INTEL_STALL_SECONDS", 45.0))
    momentum = _to_float(market_snapshot.get("momentum"))
    momentum_break_threshold = float(getattr(cfg, "EXIT_INTEL_STALL_MOMENTUM_BREAK", -0.001))
    if momentum is None:
        momentum_break = bool(market_snapshot.get("momentum_break", False))
    else:
        momentum_break = (momentum <= momentum_break_threshold) if side == "BUY" else (momentum >= -momentum_break_threshold)
    stalled_long_enough = (now_ts - float(updated_best_ts or now_ts)) >= stall_seconds
    if progress is not None and progress >= stall_target_pct and stalled_long_enough and momentum_break:
        action_name = str(getattr(cfg, "EXIT_INTEL_STALL_ACTION", "PARTIAL_EXIT")).upper()
        partial_fraction = float(getattr(cfg, "EXIT_INTEL_PARTIAL_EXIT_FRACTION", 0.5))
        exit_qty_units = max(1, int(round(qty_units * partial_fraction)))
        if action_name == "FULL_EXIT" or qty_units <= 1:
            action = ExitAction.FULL_EXIT
            exit_qty_units = qty_units
        else:
            action = ExitAction.PARTIAL_EXIT
            exit_qty_units = min(exit_qty_units, max(1, qty_units - 1))
        if safe_mode:
            state_patch["reason_codes"] = ["safe_mode_restricted", safe_reason or "safe_mode"]
            after_plan = dict(before_plan)
            after_plan.update(state_patch)
            return ExitDecision(
                action=ExitAction.NOOP,
                reason_codes=("safe_mode_restricted", safe_reason or "safe_mode"),
                before_plan=before_plan,
                after_plan=after_plan,
                state_patch=state_patch,
                safe_mode=True,
            )
        state_patch.update(
            {
                "exit_intel_phase": "STALL_EXIT",
                "last_action_ts": now_ts,
                "reason_codes": ["stall_near_target"],
            }
        )
        after_plan = dict(before_plan)
        after_plan.update(state_patch)
        return ExitDecision(
            action=action,
            reason_codes=("stall_near_target",),
            before_plan=before_plan,
            after_plan=after_plan,
            state_patch=state_patch,
            exit_qty_units=exit_qty_units,
            safe_mode=safe_mode,
        )

    if safe_mode and safe_reason:
        state_patch["reason_codes"] = [f"safe_mode:{safe_reason}"]
    after_plan = dict(before_plan)
    after_plan.update(state_patch)
    return ExitDecision(
        action=ExitAction.NOOP,
        reason_codes=tuple(state_patch.get("reason_codes") or ("no_exit_signal",)),
        before_plan=before_plan,
        after_plan=after_plan,
        state_patch=state_patch,
        safe_mode=safe_mode,
    )

