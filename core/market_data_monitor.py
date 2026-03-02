from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
import threading
import time
from typing import Callable

from config import config as cfg
from core.time_utils import compute_age_sec, now_utc_epoch


class FeedState(str, Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass(frozen=True)
class FeedSnapshot:
    state: FeedState
    reason: str
    ts_epoch: float
    last_ws_msg_time: float | None
    ws_msg_age_sec: float | None
    index_stale_tokens: int
    option_stale_tokens: int
    depth_stale_tokens: int
    tick_rate_by_symbol: dict[str, float]
    token_age_sec: dict[int, float]
    depth_age_sec: dict[int, float]

    def as_dict(self) -> dict:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "ts_epoch": self.ts_epoch,
            "last_ws_msg_time": self.last_ws_msg_time,
            "ws_msg_age_sec": self.ws_msg_age_sec,
            "index_stale_tokens": self.index_stale_tokens,
            "option_stale_tokens": self.option_stale_tokens,
            "depth_stale_tokens": self.depth_stale_tokens,
            "tick_rate_by_symbol": dict(self.tick_rate_by_symbol),
            "token_age_sec": dict(self.token_age_sec),
            "depth_age_sec": dict(self.depth_age_sec),
        }


class FeedHealth:
    def __init__(
        self,
        *,
        index_ok_age_sec: float = 1.0,
        option_ok_age_sec: float = 2.5,
        index_down_no_msg_sec: float = 3.0,
        option_down_no_msg_sec: float = 5.0,
        tick_rate_window_sec: float = 60.0,
        depth_ok_age_sec: float | None = None,
        reconnect_cooldown_sec: float = 5.0,
    ) -> None:
        self.index_ok_age_sec = float(index_ok_age_sec)
        self.option_ok_age_sec = float(option_ok_age_sec)
        self.index_down_no_msg_sec = float(index_down_no_msg_sec)
        self.option_down_no_msg_sec = float(option_down_no_msg_sec)
        self.depth_ok_age_sec = (
            float(depth_ok_age_sec)
            if depth_ok_age_sec is not None
            else max(float(index_ok_age_sec), float(option_ok_age_sec))
        )
        self.tick_rate_window_sec = max(1.0, float(tick_rate_window_sec))
        self.reconnect_cooldown_sec = max(1.0, float(reconnect_cooldown_sec))
        self._last_tick_time_by_token: dict[int, float] = {}
        self._last_depth_time_by_token: dict[int, float] = {}
        self._token_is_index: dict[int, bool] = {}
        self._token_symbol: dict[int, str] = {}
        self._symbol_tick_times: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=10000)
        )
        self._last_ws_msg_time: float | None = None
        self._last_snapshot: FeedSnapshot = FeedSnapshot(
            state=FeedState.DOWN,
            reason="no_ws_messages",
            ts_epoch=float(now_utc_epoch()),
            last_ws_msg_time=None,
            ws_msg_age_sec=None,
            index_stale_tokens=0,
            option_stale_tokens=0,
            depth_stale_tokens=0,
            tick_rate_by_symbol={},
            token_age_sec={},
            depth_age_sec={},
        )
        self._reconnect_handler: Callable[[str], bool] | None = None
        self._last_reconnect_epoch: float = 0.0
        self._lock = threading.RLock()

    def set_reconnect_handler(self, handler: Callable[[str], bool] | None) -> None:
        with self._lock:
            self._reconnect_handler = handler

    def on_ws_message(self, *, now_epoch: float | None = None) -> None:
        now = float(now_epoch if now_epoch is not None else now_utc_epoch())
        with self._lock:
            self._last_ws_msg_time = now

    def on_tick(
        self,
        *,
        token: int | str | None,
        symbol: str | None,
        ts_epoch: float | int | None,
        has_depth: bool = False,
        is_index: bool = False,
        now_epoch: float | None = None,
    ) -> None:
        now = float(now_epoch if now_epoch is not None else now_utc_epoch())
        tick_ts = _coerce_epoch(ts_epoch) or now
        token_int = _safe_int(token)
        symbol_text = str(symbol or "").strip().upper()
        with self._lock:
            self._last_ws_msg_time = now
            if token_int is not None:
                self._last_tick_time_by_token[token_int] = tick_ts
                if symbol_text:
                    self._token_symbol[token_int] = symbol_text
                if bool(is_index) or symbol_text in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                    self._token_is_index[token_int] = True
                elif token_int not in self._token_is_index:
                    self._token_is_index[token_int] = False
                if has_depth:
                    self._last_depth_time_by_token[token_int] = tick_ts
            if symbol_text:
                points = self._symbol_tick_times[symbol_text]
                points.append(now)
                self._prune_symbol_rates_locked(now)

    def on_depth_update(
        self,
        *,
        token: int | str | None,
        ts_epoch: float | int | None = None,
        symbol: str | None = None,
        is_index: bool = False,
        now_epoch: float | None = None,
    ) -> None:
        now = float(now_epoch if now_epoch is not None else now_utc_epoch())
        token_int = _safe_int(token)
        if token_int is None:
            return
        depth_ts = _coerce_epoch(ts_epoch) or now
        symbol_text = str(symbol or "").strip().upper()
        with self._lock:
            self._last_ws_msg_time = now
            self._last_depth_time_by_token[token_int] = depth_ts
            if symbol_text:
                self._token_symbol[token_int] = symbol_text
            if bool(is_index) or symbol_text in {"NIFTY", "BANKNIFTY", "SENSEX"}:
                self._token_is_index[token_int] = True
            elif token_int not in self._token_is_index:
                self._token_is_index[token_int] = False

    def snapshot(self, *, now_epoch: float | None = None) -> FeedSnapshot:
        now = float(now_epoch if now_epoch is not None else now_utc_epoch())
        with self._lock:
            ws_age = (
                compute_age_sec(self._last_ws_msg_time, now)
                if self._last_ws_msg_time is not None
                else None
            )
            token_age_sec: dict[int, float] = {}
            depth_age_sec: dict[int, float] = {}
            index_stale = 0
            option_stale = 0
            depth_stale = 0
            has_index = False
            has_option = False
            reasons: list[str] = []

            for token, tick_ts in self._last_tick_time_by_token.items():
                age = compute_age_sec(tick_ts, now)
                if age is None:
                    continue
                token_age_sec[int(token)] = float(age)
                is_idx = bool(self._token_is_index.get(int(token), False))
                if is_idx:
                    has_index = True
                    if age > self.index_ok_age_sec:
                        index_stale += 1
                else:
                    has_option = True
                    if age > self.option_ok_age_sec:
                        option_stale += 1

            for token, depth_ts in self._last_depth_time_by_token.items():
                age = compute_age_sec(depth_ts, now)
                if age is None:
                    continue
                depth_age_sec[int(token)] = float(age)
                if age > self.depth_ok_age_sec:
                    depth_stale += 1

            down_threshold = (
                self.index_down_no_msg_sec
                if has_index
                else self.option_down_no_msg_sec
            )
            state: FeedState
            if ws_age is None:
                state = FeedState.DOWN
                reasons.append("no_ws_messages")
            elif ws_age > down_threshold:
                state = FeedState.DOWN
                reasons.append(f"no_ws_messages_for_{ws_age:.2f}s")
            elif index_stale > 0 or option_stale > 0 or depth_stale > 0:
                state = FeedState.DEGRADED
                if index_stale > 0:
                    reasons.append(f"index_stale_tokens={index_stale}")
                if option_stale > 0:
                    reasons.append(f"option_stale_tokens={option_stale}")
                if depth_stale > 0:
                    reasons.append(f"depth_stale_tokens={depth_stale}")
            else:
                state = FeedState.OK
                reasons.append("healthy")

            tick_rate = self._tick_rate_locked(now)
            snap = FeedSnapshot(
                state=state,
                reason=";".join(reasons),
                ts_epoch=now,
                last_ws_msg_time=self._last_ws_msg_time,
                ws_msg_age_sec=(float(ws_age) if ws_age is not None else None),
                index_stale_tokens=int(index_stale),
                option_stale_tokens=int(option_stale),
                depth_stale_tokens=int(depth_stale),
                tick_rate_by_symbol=tick_rate,
                token_age_sec=token_age_sec,
                depth_age_sec=depth_age_sec,
            )
            self._last_snapshot = snap
            return snap

    def gate_live_entries(
        self,
        *,
        advisory_only: bool = False,
        now_epoch: float | None = None,
    ) -> tuple[bool, str, FeedSnapshot]:
        snap = self.snapshot(now_epoch=now_epoch)
        if snap.state == FeedState.OK:
            return True, "ok", snap
        if advisory_only and snap.state == FeedState.DEGRADED:
            return True, "advisory_only_degraded", snap
        return False, f"{snap.state.value.lower()}:{snap.reason}", snap

    def advisory_allowed(self, *, now_epoch: float | None = None) -> bool:
        return self.snapshot(now_epoch=now_epoch).state == FeedState.DEGRADED

    def maybe_trigger_reconnect(self, *, reason_prefix: str, now_epoch: float | None = None) -> bool:
        now = float(now_epoch if now_epoch is not None else now_utc_epoch())
        with self._lock:
            snap = self.snapshot(now_epoch=now)
            if snap.state != FeedState.DOWN:
                return False
            if (now - self._last_reconnect_epoch) < self.reconnect_cooldown_sec:
                return False
            self._last_reconnect_epoch = now
            handler = self._reconnect_handler
        if not callable(handler):
            return False
        try:
            return bool(handler(f"{reason_prefix}:{snap.reason}"))
        except Exception:
            return False

    def _prune_symbol_rates_locked(self, now_epoch: float) -> None:
        cutoff = float(now_epoch) - self.tick_rate_window_sec
        for points in self._symbol_tick_times.values():
            while points and points[0] < cutoff:
                points.popleft()

    def _tick_rate_locked(self, now_epoch: float) -> dict[str, float]:
        self._prune_symbol_rates_locked(now_epoch)
        out: dict[str, float] = {}
        window = self.tick_rate_window_sec
        for symbol, points in self._symbol_tick_times.items():
            if not points:
                continue
            out[str(symbol)] = round(float(len(points)) / float(window), 6)
        return out


def _safe_int(value) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _coerce_epoch(value) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
        if out > 1e12:
            out = out / 1000.0
        return out
    except Exception:
        pass
    try:
        if hasattr(value, "timestamp"):
            out = float(value.timestamp())
            if out > 1e12:
                out = out / 1000.0
            return out
    except Exception:
        return None
    return None


_DEFAULT_MONITOR: FeedHealth | None = None
_DEFAULT_LOCK = threading.Lock()


def get_feed_health_monitor() -> FeedHealth:
    global _DEFAULT_MONITOR
    if _DEFAULT_MONITOR is None:
        with _DEFAULT_LOCK:
            if _DEFAULT_MONITOR is None:
                _DEFAULT_MONITOR = FeedHealth(
                    index_ok_age_sec=float(
                        getattr(cfg, "FEED_HEALTH_INDEX_OK_AGE_SEC", 1.0)
                    ),
                    option_ok_age_sec=float(
                        getattr(cfg, "FEED_HEALTH_OPTION_OK_AGE_SEC", 2.5)
                    ),
                    index_down_no_msg_sec=float(
                        getattr(cfg, "FEED_HEALTH_INDEX_DOWN_NO_MSG_SEC", 3.0)
                    ),
                    option_down_no_msg_sec=float(
                        getattr(cfg, "FEED_HEALTH_OPTION_DOWN_NO_MSG_SEC", 5.0)
                    ),
                    depth_ok_age_sec=float(
                        getattr(cfg, "FEED_HEALTH_DEPTH_OK_AGE_SEC", 2.5)
                    ),
                    reconnect_cooldown_sec=float(
                        getattr(cfg, "FEED_HEALTH_RECONNECT_COOLDOWN_SEC", 5.0)
                    ),
                )
    return _DEFAULT_MONITOR


def get_feed_health_snapshot(*, now_epoch: float | None = None) -> dict:
    return get_feed_health_monitor().snapshot(now_epoch=now_epoch).as_dict()


def live_entry_gate(
    *,
    advisory_only: bool = False,
    monitor: FeedHealth | None = None,
    now_epoch: float | None = None,
) -> tuple[bool, str, dict]:
    feed = monitor or get_feed_health_monitor()
    allowed, reason, snap = feed.gate_live_entries(
        advisory_only=advisory_only,
        now_epoch=now_epoch,
    )
    return allowed, reason, snap.as_dict()


def record_tick(
    *,
    token: int | str | None,
    symbol: str | None,
    ts_epoch: float | int | None,
    has_depth: bool = False,
    is_index: bool = False,
    bid: float | int | None = None,
    ask: float | int | None = None,
    ltp: float | int | None = None,
    depth_ok: bool | None = None,
    now_epoch: float | None = None,
    monitor: FeedHealth | None = None,
) -> None:
    feed = monitor or get_feed_health_monitor()
    feed.on_tick(
        token=token,
        symbol=symbol,
        ts_epoch=ts_epoch,
        has_depth=has_depth,
        is_index=is_index,
        now_epoch=now_epoch,
    )
    try:
        from core.feed.runtime import observe_runtime_feed_quote, observe_runtime_feed_tick

        observe_runtime_feed_tick(
            symbol=symbol,
            token=token,
            ts_epoch=(now_epoch if now_epoch is not None else ts_epoch),
        )
        if (
            bid is not None
            or ask is not None
            or ltp is not None
            or depth_ok is not None
            or has_depth
        ):
            observe_runtime_feed_quote(
                symbol=symbol,
                token=token,
                bid=bid,
                ask=ask,
                ltp=ltp,
                ts_epoch=(now_epoch if now_epoch is not None else ts_epoch),
                depth_ok=depth_ok if isinstance(depth_ok, bool) else bool(has_depth),
            )
    except Exception:
        pass


def record_depth(
    *,
    token: int | str | None,
    ts_epoch: float | int | None = None,
    symbol: str | None = None,
    is_index: bool = False,
    now_epoch: float | None = None,
    monitor: FeedHealth | None = None,
) -> None:
    feed = monitor or get_feed_health_monitor()
    feed.on_depth_update(
        token=token,
        ts_epoch=ts_epoch,
        symbol=symbol,
        is_index=is_index,
        now_epoch=now_epoch,
    )
