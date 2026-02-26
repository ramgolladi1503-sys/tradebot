"""Migration note:
Dynamic spread guard with volatility-aware limits, opening-auction protection,
illiquidity detection, and cached volatility computation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from math import sqrt
from threading import RLock
import time
from typing import Any

from config import config as cfg
from core import session_calendar


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _normalize_instrument(value: Any) -> str:
    text = str(value or "").strip().upper()
    return text or "UNKNOWN"


def _bar_timestamp_epoch(bar: dict[str, Any]) -> float | None:
    for key in ("ts", "timestamp", "time", "datetime"):
        raw = bar.get(key)
        if raw is None:
            continue
        if isinstance(raw, datetime):
            dt = raw
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=session_calendar.get_session().tz)
            return float(dt.timestamp())
        value = _to_float(raw)
        if value is None:
            continue
        if value > 1e12:
            value = value / 1000.0
        return float(value)
    return None


def _bar_value(bar: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        if key in bar:
            out = _to_float(bar.get(key))
            if out is not None:
                return out
    return None


@dataclass(frozen=True)
class SpreadGuardDecision:
    allowed: bool
    reason_code: str
    reason: str
    spread_pct: float | None = None
    max_spread_pct: float | None = None
    atr_ratio: float | None = None
    stddev_ratio: float | None = None
    volatility_source: str | None = None
    opening_auction: bool = False
    illiquid: bool = False
    volatility_critical: bool = False
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "reason_code": self.reason_code,
            "reason": self.reason,
            "spread_pct": self.spread_pct,
            "max_spread_pct": self.max_spread_pct,
            "atr_ratio": self.atr_ratio,
            "stddev_ratio": self.stddev_ratio,
            "volatility_source": self.volatility_source,
            "opening_auction": bool(self.opening_auction),
            "illiquid": bool(self.illiquid),
            "volatility_critical": bool(self.volatility_critical),
            "context": dict(self.context or {}),
        }


@dataclass
class _VolatilityCacheEntry:
    bars_count: int
    last_bar_ts: float | None
    computed_at: float
    atr_ratio: float | None
    stddev_ratio: float | None
    source: str | None


class SpreadGuard:
    def __init__(self):
        self._lock = RLock()
        self._vol_cache: dict[str, _VolatilityCacheEntry] = {}
        self._cache_hits = 0
        self._cache_misses = 0

    @property
    def cache_stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "entries": len(self._vol_cache),
                "hits": int(self._cache_hits),
                "misses": int(self._cache_misses),
            }

    @staticmethod
    def _is_opening_auction(
        *,
        market_open: bool,
        now_dt: datetime | None,
        segment: str | None,
        minutes_since_open_override: int | None,
    ) -> bool:
        if not bool(getattr(cfg, "SPREAD_GUARD_ENABLE_OPENING_AUCTION", True)):
            return False
        opening_minutes = max(0, int(getattr(cfg, "SPREAD_GUARD_OPENING_AUCTION_MIN", 5)))
        if opening_minutes <= 0:
            return False
        if not market_open:
            return False
        if minutes_since_open_override is not None:
            elapsed = int(max(0, minutes_since_open_override))
        else:
            elapsed = int(session_calendar.minutes_since_open(now_dt=now_dt, segment=segment))
        return elapsed < opening_minutes

    @staticmethod
    def _compute_atr_ratio(bars: list[dict[str, Any]], period: int, reference_price: float) -> float | None:
        if period <= 0:
            return None
        if len(bars) < period + 1:
            return None
        recent = bars[-(period + 1) :]
        trs: list[float] = []
        for i in range(1, len(recent)):
            row = recent[i]
            prev = recent[i - 1]
            high = _bar_value(row, "high", "h")
            low = _bar_value(row, "low", "l")
            close_prev = _bar_value(prev, "close", "c", "ltp")
            if high is None or low is None:
                return None
            if close_prev is None:
                close_prev = (high + low) / 2.0
            tr = max(
                high - low,
                abs(high - close_prev),
                abs(low - close_prev),
            )
            trs.append(max(0.0, tr))
        if not trs:
            return None
        atr = sum(trs) / float(len(trs))
        if reference_price <= 0:
            return None
        return max(0.0, atr / reference_price)

    @staticmethod
    def _compute_stddev_ratio(bars: list[dict[str, Any]], period: int, reference_price: float) -> float | None:
        if period <= 1:
            return None
        if len(bars) < period + 1:
            return None
        recent = bars[-(period + 1) :]
        closes: list[float] = []
        for row in recent:
            close = _bar_value(row, "close", "c", "ltp")
            if close is None:
                return None
            closes.append(float(close))
        if len(closes) < 2:
            return None
        rets: list[float] = []
        for i in range(1, len(closes)):
            prev = closes[i - 1]
            curr = closes[i]
            if prev <= 0:
                continue
            rets.append((curr - prev) / prev)
        if not rets:
            return None
        mean = sum(rets) / float(len(rets))
        var = sum((x - mean) ** 2 for x in rets) / float(len(rets))
        sigma = sqrt(max(var, 0.0))
        if reference_price <= 0:
            return None
        return max(0.0, sigma)

    def _volatility_from_bars(
        self,
        *,
        instrument: str,
        bars: list[dict[str, Any]] | None,
        reference_price: float,
        now_epoch: float,
    ) -> tuple[float | None, float | None, str | None]:
        if not bars:
            return None, None, None
        period = max(2, int(getattr(cfg, "SPREAD_GUARD_VOL_PERIOD", 20)))
        last_ts = _bar_timestamp_epoch(bars[-1]) if bars else None
        cache_ttl = max(0.0, float(getattr(cfg, "SPREAD_GUARD_CACHE_TTL_SEC", 15.0)))
        key = _normalize_instrument(instrument)

        with self._lock:
            cached = self._vol_cache.get(key)
            if (
                cached is not None
                and cached.bars_count == len(bars)
                and cached.last_bar_ts == last_ts
                and (now_epoch - cached.computed_at) <= cache_ttl
            ):
                self._cache_hits += 1
                return cached.atr_ratio, cached.stddev_ratio, cached.source

        atr_ratio = self._compute_atr_ratio(bars, period, reference_price)
        stddev_ratio = self._compute_stddev_ratio(bars, period, reference_price)

        method = str(getattr(cfg, "SPREAD_GUARD_VOL_METHOD", "ATR")).strip().upper()
        source: str | None = None
        if method == "STDDEV" and stddev_ratio is not None:
            source = "STDDEV"
        elif method == "ATR" and atr_ratio is not None:
            source = "ATR"
        elif atr_ratio is not None:
            source = "ATR"
        elif stddev_ratio is not None:
            source = "STDDEV"

        with self._lock:
            self._cache_misses += 1
            self._vol_cache[key] = _VolatilityCacheEntry(
                bars_count=len(bars),
                last_bar_ts=last_ts,
                computed_at=now_epoch,
                atr_ratio=atr_ratio,
                stddev_ratio=stddev_ratio,
                source=source,
            )
        return atr_ratio, stddev_ratio, source

    def evaluate(
        self,
        *,
        bid: float | None,
        ask: float | None,
        ltp: float | None,
        instrument: str | None = None,
        bars: list[dict[str, Any]] | None = None,
        max_spread_pct_override: float | None = None,
        now_dt: datetime | None = None,
        segment: str | None = None,
        market_open: bool | None = None,
        minutes_since_open_override: int | None = None,
        volume: float | None = None,
        avg_volume: float | None = None,
    ) -> SpreadGuardDecision:
        if not bool(getattr(cfg, "SPREAD_GUARD_ENABLE", True)):
            return SpreadGuardDecision(True, "DISABLED", "spread_guard_disabled")

        b = _to_float(bid)
        a = _to_float(ask)
        p = _to_float(ltp)
        if b is None or a is None or p is None or b <= 0.0 or a <= 0.0 or p <= 0.0 or a < b:
            return SpreadGuardDecision(
                False,
                "INVALID_QUOTE",
                "invalid_quote_for_spread_guard",
                spread_pct=None,
                max_spread_pct=None,
            )

        spread_pct = max(0.0, (a - b) / p)
        now_epoch = float(time.time())
        inst = _normalize_instrument(instrument)

        current_market_open = (
            bool(session_calendar.is_open(now_dt=now_dt, segment=segment))
            if market_open is None
            else bool(market_open)
        )
        opening_auction = self._is_opening_auction(
            market_open=current_market_open,
            now_dt=now_dt,
            segment=segment,
            minutes_since_open_override=minutes_since_open_override,
        )
        if opening_auction:
            return SpreadGuardDecision(
                False,
                "OPENING_AUCTION_GUARD",
                "opening_auction_guard_active",
                spread_pct=spread_pct,
                max_spread_pct=max_spread_pct_override,
                opening_auction=True,
                context={"minutes_gate": int(getattr(cfg, "SPREAD_GUARD_OPENING_AUCTION_MIN", 5))},
            )

        volume_value = _to_float(volume)
        avg_volume_value = _to_float(avg_volume)
        if bool(getattr(cfg, "SPREAD_GUARD_ENABLE_ILLIQUID_CHECK", True)):
            min_volume = max(0.0, float(getattr(cfg, "SPREAD_GUARD_MIN_VOLUME", 1.0)))
            min_volume_ratio = max(0.0, float(getattr(cfg, "SPREAD_GUARD_MIN_VOLUME_RATIO", 0.1)))
            illiquid_spread = float(getattr(cfg, "SPREAD_GUARD_ILLIQUID_SPREAD_PCT", 0.04))
            low_abs_volume = volume_value is not None and volume_value < min_volume
            low_rel_volume = (
                volume_value is not None
                and avg_volume_value is not None
                and avg_volume_value > 0
                and (volume_value / avg_volume_value) < min_volume_ratio
            )
            spread_only_signal = (
                spread_pct >= illiquid_spread
                and (volume_value is not None or avg_volume_value is not None)
            )
            if low_abs_volume or low_rel_volume or spread_only_signal:
                return SpreadGuardDecision(
                    False,
                    "ILLIQUID_INSTRUMENT",
                    "illiquid_instrument_detected",
                    spread_pct=spread_pct,
                    max_spread_pct=max_spread_pct_override,
                    illiquid=True,
                    context={
                        "volume": volume_value,
                        "avg_volume": avg_volume_value,
                        "min_volume": min_volume,
                        "min_volume_ratio": min_volume_ratio,
                        "illiquid_spread_pct": illiquid_spread,
                    },
                )

        atr_ratio, stddev_ratio, source = self._volatility_from_bars(
            instrument=inst,
            bars=bars,
            reference_price=p,
            now_epoch=now_epoch,
        )

        vol_factor = float(getattr(cfg, "SPREAD_GUARD_VOL_FACTOR", 1.0))
        atr_component = atr_ratio
        if atr_component is None and stddev_ratio is not None:
            stddev_mult = float(getattr(cfg, "SPREAD_GUARD_STDDEV_TO_ATR_MULT", 1.0))
            atr_component = max(0.0, stddev_ratio * stddev_mult)

        base_spread = (
            float(max_spread_pct_override)
            if max_spread_pct_override is not None
            else float(getattr(cfg, "SPREAD_GUARD_BASE_SPREAD_PCT", getattr(cfg, "MAX_SPREAD_PCT", 0.015)))
        )
        dynamic_spread = base_spread
        if atr_component is not None:
            dynamic_spread = base_spread + (vol_factor * atr_component)
        dynamic_floor = float(getattr(cfg, "SPREAD_GUARD_DYNAMIC_MIN_PCT", 0.001))
        dynamic_cap = float(getattr(cfg, "SPREAD_GUARD_DYNAMIC_MAX_PCT", 0.08))
        if max_spread_pct_override is not None:
            dynamic_cap = max(dynamic_cap, float(max_spread_pct_override))
        dynamic_spread = max(dynamic_floor, min(dynamic_cap, dynamic_spread))

        critical_vol = float(getattr(cfg, "SPREAD_GUARD_CRITICAL_VOL_PCT", 0.03))
        effective_vol = atr_component if atr_component is not None else stddev_ratio
        if effective_vol is not None and effective_vol > critical_vol:
            return SpreadGuardDecision(
                False,
                "VOLATILITY_CRITICAL",
                "volatility_above_critical_threshold",
                spread_pct=spread_pct,
                max_spread_pct=dynamic_spread,
                atr_ratio=atr_ratio,
                stddev_ratio=stddev_ratio,
                volatility_source=source,
                volatility_critical=True,
                context={"critical_vol_pct": critical_vol},
            )

        if spread_pct > dynamic_spread:
            return SpreadGuardDecision(
                False,
                "WIDE_SPREAD",
                "spread_exceeds_dynamic_threshold",
                spread_pct=spread_pct,
                max_spread_pct=dynamic_spread,
                atr_ratio=atr_ratio,
                stddev_ratio=stddev_ratio,
                volatility_source=source,
                context={"base_spread_pct": base_spread, "vol_factor": vol_factor},
            )

        return SpreadGuardDecision(
            True,
            "OK",
            "spread_within_dynamic_threshold",
            spread_pct=spread_pct,
            max_spread_pct=dynamic_spread,
            atr_ratio=atr_ratio,
            stddev_ratio=stddev_ratio,
            volatility_source=source,
            context={"base_spread_pct": base_spread, "vol_factor": vol_factor},
        )
