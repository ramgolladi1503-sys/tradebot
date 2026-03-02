from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time
from typing import Callable


def _coerce_ts(ts: float | int | None, now_fn: Callable[[], float]) -> float:
    if ts is None:
        return float(now_fn())
    val = float(ts)
    if val > 1_000_000_000_000:
        val = val / 1000.0
    return val


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if math.isnan(out):
            return None
        return out
    except Exception:
        return None


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    vals = sorted(float(v) for v in values)
    if len(vals) == 1:
        return vals[0]
    rank = (len(vals) - 1) * (float(p) / 100.0)
    lo = int(math.floor(rank))
    hi = int(math.ceil(rank))
    if lo == hi:
        return vals[lo]
    frac = rank - lo
    return vals[lo] * (1.0 - frac) + vals[hi] * frac


class RollingWindowStats:
    def __init__(self, window_sec: int, now_fn: Callable[[], float] | None = None):
        self.window_sec = max(1, int(window_sec))
        self.now_fn = now_fn or time.time
        self._points: deque[tuple[float, float]] = deque()

    def add(self, value: float, ts: float | None = None) -> None:
        v = _safe_float(value)
        if v is None:
            return
        t = _coerce_ts(ts, self.now_fn)
        self._points.append((t, float(v)))
        self.purge_old(now=t)

    def purge_old(self, now: float | None = None) -> None:
        cutoff_now = _coerce_ts(now, self.now_fn)
        cutoff = cutoff_now - float(self.window_sec)
        while self._points and self._points[0][0] < cutoff:
            self._points.popleft()

    def count(self) -> int:
        self.purge_old()
        return len(self._points)

    def mean(self) -> float | None:
        self.purge_old()
        if not self._points:
            return None
        vals = [v for _, v in self._points]
        return float(sum(vals) / len(vals))

    def p50(self) -> float | None:
        self.purge_old()
        return _percentile([v for _, v in self._points], 50.0)

    def p95(self) -> float | None:
        self.purge_old()
        return _percentile([v for _, v in self._points], 95.0)


@dataclass(frozen=True)
class _QuoteObs:
    bid: float | None
    ask: float | None
    ltp: float | None
    ts: float
    depth_ok: bool | None


class FeedGroupMetrics:
    """
    Rolling per-group feed metrics with an injectable clock.
    """

    def __init__(
        self,
        now_fn: Callable[[], float] | None = None,
        *,
        window_sec: int = 300,
        recent_age_sec: float = 5.0,
    ) -> None:
        self.now_fn = now_fn or time.time
        self.window_sec = max(1, int(window_sec))
        self.recent_age_sec = max(0.1, float(recent_age_sec))

        self.last_tick_ts_by_token: dict[str, float] = {}
        self.last_quote_ts_by_token: dict[str, float] = {}
        self._latest_quote_by_token: dict[str, _QuoteObs] = {}
        self.last_ws_ts: float | None = None
        self._tick_events: deque[float] = deque()

        self._spread_pct_stats = RollingWindowStats(self.window_sec, self.now_fn)
        self._depth_missing_stats = RollingWindowStats(self.window_sec, self.now_fn)

    def _token_key(self, token: str | int | None) -> str:
        if token is None:
            return "unknown"
        try:
            return str(int(token))
        except Exception:
            return str(token)

    def _purge_tick_events(self, now_ts: float) -> None:
        cutoff = now_ts - float(self.window_sec)
        while self._tick_events and self._tick_events[0] < cutoff:
            self._tick_events.popleft()

    def observe_ws(self, ts: float | int | None = None) -> None:
        self.last_ws_ts = _coerce_ts(ts, self.now_fn)

    def observe_tick(self, token: str, ts: float | int | None = None) -> None:
        now_ts = _coerce_ts(ts, self.now_fn)
        token_key = self._token_key(token)
        self.last_ws_ts = now_ts
        self.last_tick_ts_by_token[token_key] = now_ts
        self._tick_events.append(now_ts)
        self._purge_tick_events(now_ts)

    def observe_quote(
        self,
        token: str,
        bid: float | None,
        ask: float | None,
        ltp: float | None,
        ts: float | int | None = None,
        depth_ok: bool | None = None,
    ) -> None:
        now_ts = _coerce_ts(ts, self.now_fn)
        token_key = self._token_key(token)
        bid_v = _safe_float(bid)
        ask_v = _safe_float(ask)
        ltp_v = _safe_float(ltp)

        self.last_ws_ts = now_ts
        self.last_quote_ts_by_token[token_key] = now_ts
        self._latest_quote_by_token[token_key] = _QuoteObs(
            bid=bid_v,
            ask=ask_v,
            ltp=ltp_v,
            ts=now_ts,
            depth_ok=depth_ok if isinstance(depth_ok, bool) else None,
        )

        if bid_v is not None and ask_v is not None:
            base = ltp_v if ltp_v is not None and ltp_v > 0 else (bid_v + ask_v) / 2.0
            if base is not None and base > 0:
                spread_pct = (ask_v - bid_v) / base
                self._spread_pct_stats.add(spread_pct, ts=now_ts)
        if depth_ok is not None:
            self._depth_missing_stats.add(0.0 if depth_ok else 1.0, ts=now_ts)

    def snapshot(self) -> dict:
        now_ts = _coerce_ts(None, self.now_fn)
        self._purge_tick_events(now_ts)

        ws_age = None if self.last_ws_ts is None else max(0.0, now_ts - self.last_ws_ts)

        tick_ages = [max(0.0, now_ts - ts) for ts in self.last_tick_ts_by_token.values()]
        quote_ages = [max(0.0, now_ts - ts) for ts in self.last_quote_ts_by_token.values()]
        token_count = len(self.last_tick_ts_by_token)

        tokens_recent_pct = None
        if token_count > 0:
            recent = sum(1 for age in tick_ages if age <= self.recent_age_sec)
            tokens_recent_pct = (float(recent) / float(token_count)) * 100.0

        tick_age_p50 = _percentile(tick_ages, 50.0)
        tick_age_p95 = _percentile(tick_ages, 95.0)
        tick_age_mean = (
            (float(sum(tick_ages)) / float(len(tick_ages))) if tick_ages else None
        )
        quote_age_p95 = _percentile(quote_ages, 95.0)

        spread_p95 = self._spread_pct_stats.p95()
        depth_missing_mean = self._depth_missing_stats.mean()
        depth_missing_pct = (
            (float(depth_missing_mean) * 100.0)
            if depth_missing_mean is not None
            else None
        )

        tick_rate_tps = float(len(self._tick_events)) / float(self.window_sec)

        return {
            "ts_epoch": now_ts,
            "ws_age": ws_age,
            "tick_age_p50": tick_age_p50,
            "tick_age_p95": tick_age_p95,
            "tick_age_mean": tick_age_mean,
            "quote_age_p95": quote_age_p95,
            "spread_p95": spread_p95,
            "depth_missing_pct": depth_missing_pct,
            "tokens_total": token_count,
            "tokens_recent_pct": tokens_recent_pct,
            "tick_rate_tps": tick_rate_tps,
        }
