from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

from config import config as cfg

FeedGroupKey = str

_INDEX_ROOTS = ("BANKNIFTY", "NIFTY", "SENSEX")
_GROUP_INDEX_PREFIX = "INDEX:"
_GROUP_OPTION_PREFIX = "OPT:"


class FeedHealthState(Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass(frozen=True)
class FeedGroupThreshold:
    ok_age_sec: float
    down_no_msg_sec: float
    max_quote_age_sec: float | None = None
    max_spread_pct: float | None = None
    require_depth: bool = False


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:
            return None
        return out
    except Exception:
        return None


def _coerce_epoch(value) -> float | None:
    val = _safe_float(value)
    if val is None:
        return None
    if val > 1e12:
        return val / 1000.0
    return val


def _age_sec(now_epoch: float, then_epoch: float | None) -> float | None:
    if then_epoch is None:
        return None
    age = float(now_epoch) - float(then_epoch)
    return max(age, 0.0)


def _token_key(token) -> str:
    if token is None:
        return "unknown"
    try:
        return str(int(token))
    except Exception:
        return str(token)


def _upper_text(value) -> str:
    return str(value or "").strip().upper()


def _symbol_root(text: str) -> str | None:
    raw = _upper_text(text)
    compact = raw.replace(" ", "")
    if compact in {"BANKNIFTY", "NIFTYBANK"}:
        return "BANKNIFTY"
    if compact in {"NIFTY", "NIFTY50"}:
        return "NIFTY"
    if compact == "SENSEX":
        return "SENSEX"
    for root in _INDEX_ROOTS:
        if root in raw:
            return root
    return None


def _looks_option_symbol(text: str) -> bool:
    raw = _upper_text(text)
    if not raw:
        return True
    if "|" in raw:
        parts = [x for x in raw.split("|") if x]
        if len(parts) >= 4:
            return True
    return ("CE" in raw) or ("PE" in raw)


def classify_group(symbol: str) -> FeedGroupKey:
    """
    Classify symbols into feed groups used by runtime health gating.
    Unknown groups are fail-closed at execution time.
    """
    raw = _upper_text(symbol)
    if not raw:
        return f"{_GROUP_OPTION_PREFIX}UNKNOWN"
    root = _symbol_root(raw)
    if root is None:
        return f"{_GROUP_OPTION_PREFIX}UNKNOWN"
    if raw == root:
        return f"{_GROUP_INDEX_PREFIX}{root}"
    if _looks_option_symbol(raw):
        return f"{_GROUP_OPTION_PREFIX}{root}"
    if "INDEX" in raw or "NSE:" in raw or "BSE:" in raw:
        return f"{_GROUP_INDEX_PREFIX}{root}"
    return f"{_GROUP_OPTION_PREFIX}{root}"


class FeedGroupMetrics:
    """
    Lightweight per-group metrics collector used by FeedHealthMachine.
    """

    def __init__(
        self,
        *,
        group_key: FeedGroupKey,
        now_fn: Callable[[], float] | None = None,
        tick_rate_window_sec: float = 60.0,
    ) -> None:
        self.group_key = str(group_key)
        self.now_fn = now_fn or time.time
        self.tick_rate_window_sec = max(1.0, float(tick_rate_window_sec))
        self._last_ws_ts: float | None = None
        self._last_tick_ts_by_token: dict[str, float] = {}
        self._last_quote_ts_by_token: dict[str, float] = {}
        self._latest_quote_by_token: dict[str, dict] = {}
        self._tick_points: deque[float] = deque(maxlen=20000)
        self._lock = threading.RLock()

    def observe_ws(self, ts: float | int | None = None) -> None:
        now = _coerce_epoch(ts)
        if now is None:
            now = _coerce_epoch(self.now_fn())
        if now is None:
            return
        with self._lock:
            self._last_ws_ts = float(now)

    def observe_tick(self, token, ts: float | int | None = None) -> None:
        now = _coerce_epoch(ts)
        if now is None:
            now = _coerce_epoch(self.now_fn())
        if now is None:
            return
        token_id = _token_key(token)
        with self._lock:
            self._last_ws_ts = float(now)
            self._last_tick_ts_by_token[token_id] = float(now)
            self._tick_points.append(float(now))
            self._prune_ticks_locked(float(now))

    def observe_quote(
        self,
        token,
        bid=None,
        ask=None,
        ltp=None,
        ts: float | int | None = None,
        depth_ok: bool | None = None,
    ) -> None:
        now = _coerce_epoch(ts)
        if now is None:
            now = _coerce_epoch(self.now_fn())
        if now is None:
            return
        token_id = _token_key(token)
        with self._lock:
            self._last_ws_ts = float(now)
            self._last_quote_ts_by_token[token_id] = float(now)
            self._latest_quote_by_token[token_id] = {
                "bid": _safe_float(bid),
                "ask": _safe_float(ask),
                "ltp": _safe_float(ltp),
                "depth_ok": depth_ok if isinstance(depth_ok, bool) else None,
                "ts": float(now),
            }

    def _prune_ticks_locked(self, now_epoch: float) -> None:
        cutoff = float(now_epoch) - self.tick_rate_window_sec
        while self._tick_points and float(self._tick_points[0]) < cutoff:
            self._tick_points.popleft()

    def snapshot(self) -> dict:
        now = _coerce_epoch(self.now_fn())
        if now is None:
            now = time.time()
        with self._lock:
            self._prune_ticks_locked(float(now))
            ws_age = _age_sec(float(now), self._last_ws_ts)
            tick_ages = [
                _age_sec(float(now), ts)
                for ts in self._last_tick_ts_by_token.values()
            ]
            tick_ages = [x for x in tick_ages if x is not None]
            max_tick_age = max(tick_ages) if tick_ages else None

            latest_quote = None
            for quote in self._latest_quote_by_token.values():
                if not isinstance(quote, dict):
                    continue
                if latest_quote is None or float(quote.get("ts") or 0.0) > float(
                    latest_quote.get("ts") or 0.0
                ):
                    latest_quote = quote
            quote_age = None
            spread_pct = None
            depth_ok = None
            if isinstance(latest_quote, dict):
                quote_age = _age_sec(float(now), _coerce_epoch(latest_quote.get("ts")))
                bid = _safe_float(latest_quote.get("bid"))
                ask = _safe_float(latest_quote.get("ask"))
                ltp = _safe_float(latest_quote.get("ltp"))
                depth_ok = latest_quote.get("depth_ok")
                if bid is not None and ask is not None:
                    base = ltp
                    if base is None or base <= 0:
                        base = (bid + ask) / 2.0
                    if base and base > 0:
                        spread_pct = (ask - bid) / base

            tick_rate = round(
                float(len(self._tick_points)) / float(self.tick_rate_window_sec), 6
            )
            return {
                "group_key": self.group_key,
                "ts_epoch": float(now),
                "last_ws_ts": self._last_ws_ts,
                "ws_age_sec": ws_age,
                "tick_age_sec": max_tick_age,
                "quote_age_sec": quote_age,
                "spread_pct": spread_pct,
                "depth_ok": depth_ok,
                "tick_rate": tick_rate,
            }


class FeedHealthMachine:
    def __init__(self, *, thresholds_by_group: dict[FeedGroupKey, FeedGroupThreshold]) -> None:
        self.thresholds_by_group = dict(thresholds_by_group or {})
        self._last_by_group: dict[FeedGroupKey, dict] = {}
        self._lock = threading.RLock()

    def update_group(self, group_key: FeedGroupKey, snapshot: dict | None) -> dict:
        key = str(group_key or "")
        threshold = self.thresholds_by_group.get(key)
        if threshold is None:
            result = {
                "group_key": key,
                "state": FeedHealthState.DOWN,
                "reason": "unknown_group",
                "snapshot": dict(snapshot or {}),
            }
            with self._lock:
                self._last_by_group[key] = dict(result)
            return result

        snap = dict(snapshot or {})
        ws_age = _safe_float(snap.get("ws_age_sec"))
        tick_age = _safe_float(snap.get("tick_age_sec"))

        if ws_age is None and tick_age is None:
            state = FeedHealthState.DOWN
            reason = "no_ws_or_tick_age"
        elif (
            (ws_age is not None and ws_age > threshold.down_no_msg_sec)
            or (tick_age is not None and tick_age > threshold.down_no_msg_sec)
        ):
            state = FeedHealthState.DOWN
            parts = []
            if ws_age is not None and ws_age > threshold.down_no_msg_sec:
                parts.append(f"ws_age={ws_age:.3f}>{threshold.down_no_msg_sec:.3f}")
            if tick_age is not None and tick_age > threshold.down_no_msg_sec:
                parts.append(
                    f"tick_age={tick_age:.3f}>{threshold.down_no_msg_sec:.3f}"
                )
            reason = "down_threshold_breach:" + "|".join(parts)
        else:
            degraded_reasons: list[str] = []
            if ws_age is None or ws_age > threshold.ok_age_sec:
                degraded_reasons.append("ws_stale")
            if tick_age is None or tick_age > threshold.ok_age_sec:
                degraded_reasons.append("tick_stale")

            quote_age = _safe_float(snap.get("quote_age_sec"))
            if (
                threshold.max_quote_age_sec is not None
                and quote_age is not None
                and quote_age > threshold.max_quote_age_sec
            ):
                degraded_reasons.append("quote_stale")

            spread_pct = _safe_float(snap.get("spread_pct"))
            if (
                threshold.max_spread_pct is not None
                and spread_pct is not None
                and spread_pct > threshold.max_spread_pct
            ):
                degraded_reasons.append("spread_wide")

            depth_ok = snap.get("depth_ok")
            if threshold.require_depth and depth_ok is False:
                degraded_reasons.append("depth_missing")

            if degraded_reasons:
                state = FeedHealthState.DEGRADED
                reason = "degraded:" + "|".join(sorted(set(degraded_reasons)))
            else:
                state = FeedHealthState.OK
                reason = "ok"

        result = {
            "group_key": key,
            "state": state,
            "reason": reason,
            "snapshot": snap,
        }
        with self._lock:
            self._last_by_group[key] = dict(result)
        return result

    def last_result(self, group_key: FeedGroupKey) -> dict | None:
        with self._lock:
            val = self._last_by_group.get(str(group_key or ""))
            return dict(val) if isinstance(val, dict) else None

    def get_status(self, group_key: FeedGroupKey) -> dict:
        """
        Read-only status lookup for analytics/telemetry code.
        Does not trigger state transitions.
        """
        key = str(group_key or "")
        with self._lock:
            existing = self._last_by_group.get(key)
            if isinstance(existing, dict):
                state = existing.get("state")
                state_name = state.name if isinstance(state, FeedHealthState) else "UNKNOWN"
                return {
                    "group_key": key,
                    "state": state_name,
                    "reason": str(existing.get("reason") or ""),
                    "flap_locked": None,
                    "flap_lock_until": None,
                }
        return {
            "group_key": key,
            "state": "UNKNOWN",
            "reason": "no_state",
            "flap_locked": None,
            "flap_lock_until": None,
        }


def _group_thresholds() -> dict[FeedGroupKey, FeedGroupThreshold]:
    index_ok = float(getattr(cfg, "FEED_HEALTH_INDEX_OK_AGE_SEC", 1.0))
    option_ok = float(getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5))
    index_down = float(getattr(cfg, "FEED_HEALTH_INDEX_DOWN_NO_MSG_SEC", 3.0))
    option_down = float(getattr(cfg, "FEED_HEALTH_OPTION_DOWN_NO_MSG_SEC", 5.0))
    max_quote_age = _safe_float(getattr(cfg, "LIVE_MAX_QUOTE_AGE_SEC", None))
    max_spread_pct = _safe_float(getattr(cfg, "LIVE_MAX_SPREAD_PCT", None))
    groups: dict[FeedGroupKey, FeedGroupThreshold] = {}
    for root in _INDEX_ROOTS:
        groups[f"{_GROUP_INDEX_PREFIX}{root}"] = FeedGroupThreshold(
            ok_age_sec=index_ok,
            down_no_msg_sec=index_down,
            max_quote_age_sec=max_quote_age,
            max_spread_pct=max_spread_pct,
            require_depth=False,
        )
        groups[f"{_GROUP_OPTION_PREFIX}{root}"] = FeedGroupThreshold(
            ok_age_sec=option_ok,
            down_no_msg_sec=option_down,
            max_quote_age_sec=max_quote_age,
            max_spread_pct=max_spread_pct,
            require_depth=False,
        )
    return groups


def build_default_feed_health(
    now_fn: Callable[[], float] | None = None,
) -> tuple[FeedHealthMachine, dict[FeedGroupKey, FeedGroupMetrics]]:
    thresholds = _group_thresholds()
    machine = FeedHealthMachine(thresholds_by_group=thresholds)
    tick_window = float(getattr(cfg, "FEED_HEALTH_TICK_RATE_WINDOW_SEC", 60.0))
    metrics_map = {
        group_key: FeedGroupMetrics(
            group_key=group_key,
            now_fn=now_fn,
            tick_rate_window_sec=tick_window,
        )
        for group_key in thresholds.keys()
    }
    return machine, metrics_map


_RUNTIME_LOCK = threading.Lock()
_RUNTIME_MACHINE: FeedHealthMachine | None = None
_RUNTIME_METRICS_MAP: dict[FeedGroupKey, FeedGroupMetrics] | None = None


def get_runtime_feed_health(
    *,
    now_fn: Callable[[], float] | None = None,
) -> tuple[FeedHealthMachine, dict[FeedGroupKey, FeedGroupMetrics]]:
    global _RUNTIME_MACHINE, _RUNTIME_METRICS_MAP
    if _RUNTIME_MACHINE is None or _RUNTIME_METRICS_MAP is None:
        with _RUNTIME_LOCK:
            if _RUNTIME_MACHINE is None or _RUNTIME_METRICS_MAP is None:
                _RUNTIME_MACHINE, _RUNTIME_METRICS_MAP = build_default_feed_health(
                    now_fn=now_fn
                )
    return _RUNTIME_MACHINE, _RUNTIME_METRICS_MAP


def observe_runtime_feed_tick(
    *,
    symbol: str | None,
    token: int | str | None,
    ts_epoch: float | int | None,
) -> None:
    group_key = classify_group(str(symbol or ""))
    machine, metrics_map = get_runtime_feed_health()
    metrics = metrics_map.get(group_key)
    if metrics is None:
        return
    metrics.observe_ws(ts=ts_epoch)
    metrics.observe_tick(token, ts=ts_epoch)
    machine.update_group(group_key, metrics.snapshot())


def observe_runtime_feed_quote(
    *,
    symbol: str | None,
    token: int | str | None,
    bid=None,
    ask=None,
    ltp=None,
    ts_epoch: float | int | None = None,
    depth_ok: bool | None = None,
) -> None:
    group_key = classify_group(str(symbol or ""))
    machine, metrics_map = get_runtime_feed_health()
    metrics = metrics_map.get(group_key)
    if metrics is None:
        return
    metrics.observe_ws(ts=ts_epoch)
    metrics.observe_tick(token, ts=ts_epoch)
    metrics.observe_quote(
        token=token,
        bid=bid,
        ask=ask,
        ltp=ltp,
        ts=ts_epoch,
        depth_ok=depth_ok,
    )
    machine.update_group(group_key, metrics.snapshot())
