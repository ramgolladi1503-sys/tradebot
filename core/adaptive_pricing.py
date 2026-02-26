"""Migration note:
Adaptive limit pricing logic extracted for deterministic, testable behavior.
Includes queue-depth consumption, urgency, time-decay aggressiveness, retry
stepping, and max-slippage guards.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass(frozen=True)
class AdaptivePricePolicy:
    base_slippage_bps: float
    spread_mult: float
    max_buffer_pct: float
    vol_z_bps: float
    imbalance_bps: float
    atr_vol_bps_mult: float
    queue_consumption_bps: float
    urgency_bps: float
    time_decay_bps: float
    retry_step_pct: float
    max_slippage_bps: float
    min_tick: float
    queue_levels: int = 3


@dataclass(frozen=True)
class AdaptivePriceInput:
    side: str
    bid: float
    ask: float
    qty: float = 1.0
    spread_pct: float | None = None
    depth_imbalance: float | None = None
    vol_z: float | None = None
    atr_ratio: float | None = None
    depth: dict[str, Any] | None = None
    signal_strength: float | None = None
    elapsed_sec: float = 0.0
    timeout_sec: float = 0.0
    retry_index: int = 0
    max_retries: int = 0
    current_limit: float | None = None


@dataclass(frozen=True)
class AdaptivePriceResult:
    limit_price: float | None
    details: dict[str, Any] = field(default_factory=dict)


def _round_to_tick(price: float, tick_size: float) -> float:
    tick = max(_to_float(tick_size, 0.0), 0.0)
    if tick <= 0:
        return round(price, 2)
    ticks = round(price / tick)
    return round(ticks * tick, 6)


def estimate_queue_depth_consumption(
    depth: dict[str, Any] | None,
    side: str,
    qty: float,
    *,
    levels: int = 3,
) -> dict[str, float | None]:
    if not depth or not isinstance(depth, dict):
        return {
            "queue_available_qty": None,
            "queue_consumption_ratio": 0.0,
            "queue_ahead_ratio": None,
        }
    levels = max(1, int(levels))
    side_key = "sell" if str(side).upper() == "BUY" else "buy"
    book = depth.get(side_key)
    if not isinstance(book, list) or not book:
        return {
            "queue_available_qty": None,
            "queue_consumption_ratio": 0.0,
            "queue_ahead_ratio": None,
        }
    total_qty = 0.0
    top_qty = 0.0
    for idx, row in enumerate(book[:levels]):
        try:
            q = max(_to_float((row or {}).get("quantity"), 0.0), 0.0)
        except Exception:
            q = 0.0
        total_qty += q
        if idx == 0:
            top_qty = q
    qty_abs = max(_to_float(qty, 1.0), 0.0)
    consumption = qty_abs / max(total_qty, 1.0)
    ahead_ratio = top_qty / max(top_qty + qty_abs, 1.0)
    return {
        "queue_available_qty": round(total_qty, 6),
        "queue_consumption_ratio": round(_clamp(consumption, 0.0, 10.0), 6),
        "queue_ahead_ratio": round(_clamp(ahead_ratio, 0.0, 1.0), 6),
    }


def compute_urgency_score(
    *,
    signal_strength: float | None,
    retry_index: int,
    max_retries: int,
) -> float:
    signal = _clamp(_to_float(signal_strength, 0.5), 0.0, 1.0)
    retry_pressure = 0.0
    if max_retries > 0:
        retry_pressure = _clamp(float(retry_index) / float(max_retries), 0.0, 1.0)
    return _clamp((0.75 * signal) + (0.25 * retry_pressure), 0.0, 1.0)


def compute_time_decay_aggressiveness(
    *,
    elapsed_sec: float,
    timeout_sec: float,
    retry_index: int,
    max_retries: int,
) -> float:
    elapsed = max(_to_float(elapsed_sec, 0.0), 0.0)
    timeout = max(_to_float(timeout_sec, 0.0), 0.0)
    if timeout > 0:
        progress = _clamp(elapsed / timeout, 0.0, 1.0)
    elif max_retries > 0:
        progress = _clamp(float(retry_index) / float(max_retries), 0.0, 1.0)
    else:
        progress = 0.0
    # Convex curve: low early aggression, accelerates late.
    return _clamp(progress * progress, 0.0, 1.0)


def compute_adaptive_limit_price(
    data: AdaptivePriceInput,
    policy: AdaptivePricePolicy,
) -> AdaptivePriceResult:
    side = str(data.side or "").strip().upper()
    bid = _to_float(data.bid, 0.0)
    ask = _to_float(data.ask, 0.0)
    if side not in {"BUY", "SELL"}:
        return AdaptivePriceResult(None, {"reason": "bad_side"})
    if bid <= 0.0 or ask <= 0.0 or ask < bid:
        return AdaptivePriceResult(None, {"reason": "bad_quote"})

    mid = (bid + ask) / 2.0
    if mid <= 0.0:
        return AdaptivePriceResult(None, {"reason": "bad_mid"})

    spread_pct = data.spread_pct
    if spread_pct is None:
        spread_pct = (ask - bid) / mid
    spread_pct = max(0.0, _to_float(spread_pct, 0.0))

    vol_z = abs(_to_float(data.vol_z, 0.0))
    atr_ratio = max(_to_float(data.atr_ratio, 0.0), 0.0)
    depth_imb = _clamp(_to_float(data.depth_imbalance, 0.0), -1.0, 1.0)
    qty = max(_to_float(data.qty, 1.0), 1.0)

    queue = estimate_queue_depth_consumption(
        data.depth,
        side,
        qty,
        levels=policy.queue_levels,
    )
    queue_consumption = _clamp(_to_float(queue.get("queue_consumption_ratio"), 0.0), 0.0, 10.0)
    urgency = compute_urgency_score(
        signal_strength=data.signal_strength,
        retry_index=max(int(data.retry_index), 0),
        max_retries=max(int(data.max_retries), 0),
    )
    time_decay = compute_time_decay_aggressiveness(
        elapsed_sec=data.elapsed_sec,
        timeout_sec=data.timeout_sec,
        retry_index=max(int(data.retry_index), 0),
        max_retries=max(int(data.max_retries), 0),
    )

    base_buf = max(policy.base_slippage_bps, 0.0) / 10000.0
    spread_buf = min(
        max(spread_pct * max(policy.spread_mult, 0.0), 0.0),
        max(policy.max_buffer_pct, 0.0),
    )
    vol_buf = (vol_z * max(policy.vol_z_bps, 0.0) / 10000.0) + (
        atr_ratio * max(policy.atr_vol_bps_mult, 0.0)
    )
    imb_buf = abs(depth_imb) * max(policy.imbalance_bps, 0.0) / 10000.0
    queue_buf = queue_consumption * max(policy.queue_consumption_bps, 0.0) / 10000.0
    urgency_buf = urgency * max(policy.urgency_bps, 0.0) / 10000.0
    decay_buf = time_decay * max(policy.time_decay_bps, 0.0) / 10000.0

    favorable_imbalance = 0.0
    if side == "BUY" and depth_imb > 0:
        favorable_imbalance = imb_buf
    elif side == "SELL" and depth_imb < 0:
        favorable_imbalance = imb_buf

    total_buffer = max(
        0.0,
        base_buf + spread_buf + vol_buf + queue_buf + urgency_buf + decay_buf - favorable_imbalance,
    )

    if side == "BUY":
        raw_limit = ask * (1.0 + total_buffer)
    else:
        raw_limit = bid * (1.0 - total_buffer)

    retry_step = max(_to_float(policy.retry_step_pct, 0.0), 0.0)
    if data.current_limit is not None and retry_step > 0 and int(data.retry_index) > 0:
        current_limit = _to_float(data.current_limit, 0.0)
        if side == "BUY":
            stepped = current_limit * (1.0 + retry_step)
            raw_limit = max(raw_limit, stepped)
        else:
            stepped = current_limit * (1.0 - retry_step)
            raw_limit = min(raw_limit, stepped)

    guard_hit = False
    max_slippage_bps = max(_to_float(policy.max_slippage_bps, 0.0), 0.0)
    if max_slippage_bps > 0:
        slippage_cap = max_slippage_bps / 10000.0
        if side == "BUY":
            max_price = ask * (1.0 + slippage_cap)
            if raw_limit > max_price:
                raw_limit = max_price
                guard_hit = True
        else:
            min_price = bid * (1.0 - slippage_cap)
            if raw_limit < min_price:
                raw_limit = min_price
                guard_hit = True

    limit = _round_to_tick(raw_limit, policy.min_tick)
    if not math.isfinite(limit) or limit <= 0:
        return AdaptivePriceResult(None, {"reason": "bad_limit_computation"})

    return AdaptivePriceResult(
        float(limit),
        {
            "reason": "ok",
            "base_buffer": round(base_buf, 8),
            "spread_buffer": round(spread_buf, 8),
            "vol_buffer": round(vol_buf, 8),
            "imb_buffer": round(imb_buf, 8),
            "queue_buffer": round(queue_buf, 8),
            "urgency_buffer": round(urgency_buf, 8),
            "time_decay_buffer": round(decay_buf, 8),
            "total_buffer": round(total_buffer, 8),
            "spread_pct": round(spread_pct, 8),
            "atr_ratio": round(atr_ratio, 8),
            "vol_z": round(vol_z, 8),
            "depth_imbalance": round(depth_imb, 8),
            "queue_consumption_ratio": queue.get("queue_consumption_ratio"),
            "queue_available_qty": queue.get("queue_available_qty"),
            "queue_ahead_ratio": queue.get("queue_ahead_ratio"),
            "urgency_score": round(urgency, 8),
            "time_decay_aggressiveness": round(time_decay, 8),
            "retry_index": int(max(data.retry_index, 0)),
            "max_retries": int(max(data.max_retries, 0)),
            "step_pct": round(retry_step, 8),
            "max_slippage_guard_hit": bool(guard_hit),
            "max_slippage_bps": round(max_slippage_bps, 8),
            "raw_limit_price": round(raw_limit, 8),
            "limit_price": round(limit, 8),
        },
    )
