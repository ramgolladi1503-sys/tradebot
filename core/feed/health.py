from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import time

from .types import FeedGroupKey, FeedGroupType, FeedState, FeedThresholds


def _safe_float(value) -> float | None:
    try:
        if value is None:
            return None
        out = float(value)
        if out != out:  # NaN
            return None
        return out
    except Exception:
        return None


def _elapsed(now_ts: float, since_ts: float | None) -> float:
    if since_ts is None:
        return 0.0
    return max(0.0, float(now_ts) - float(since_ts))


def default_thresholds_for_group_type(group_type: FeedGroupType) -> FeedThresholds:
    common = {
        "downgrade_window_sec": 10.0,
        "upgrade_window_sec": 60.0,
        "min_hold_sec": 30.0,
        "ws_down_age_sec": 15.0,
        "flap_window_sec": 300.0,
        "flap_max_transitions": 3,
        "flap_lock_sec": 300.0,
    }
    if group_type == FeedGroupType.INDEX:
        return FeedThresholds(
            ok_age_p95=2.0,
            deg_age_p95=5.0,
            down_age_p95=8.0,
            **common,
        )
    return FeedThresholds(
        ok_age_p95=3.0,
        deg_age_p95=7.0,
        down_age_p95=10.0,
        ok_spread_p95=0.0035,
        deg_spread_p95=0.0060,
        ok_depth_missing_pct=20.0,
        deg_depth_missing_pct=40.0,
        **common,
    )


def build_default_thresholds(
    roots: tuple[str, ...] = ("NIFTY", "BANKNIFTY", "SENSEX"),
) -> dict[FeedGroupKey, FeedThresholds]:
    out: dict[FeedGroupKey, FeedThresholds] = {}
    idx_th = default_thresholds_for_group_type(FeedGroupType.INDEX)
    opt_th = default_thresholds_for_group_type(FeedGroupType.OPTIONS)
    for root in roots:
        out[FeedGroupKey(f"INDEX:{root}")] = idx_th
        out[FeedGroupKey(f"OPT:{root}")] = opt_th
    return out


@dataclass
class _GroupStatus:
    state: FeedState
    last_transition_ts: float
    transition_times: deque[float] = field(default_factory=deque)
    flap_lock_until: float | None = None

    ok_since: float | None = None
    deg_since: float | None = None
    down_since: float | None = None
    bad_ok_since: float | None = None


class FeedHealthMachine:
    def __init__(
        self,
        thresholds_by_group: dict[FeedGroupKey, FeedThresholds],
        now_fn=None,
    ) -> None:
        self.thresholds_by_group = dict(thresholds_by_group or {})
        self.now_fn = now_fn or time.time
        self._status_by_group: dict[FeedGroupKey, _GroupStatus] = {}

    def _resolve_threshold(self, group_key: FeedGroupKey) -> FeedThresholds | None:
        if group_key in self.thresholds_by_group:
            return self.thresholds_by_group[group_key]
        for key, threshold in self.thresholds_by_group.items():
            if str(key) == str(group_key):
                return threshold
        return None

    def _group_type(self, group_key: FeedGroupKey) -> FeedGroupType:
        return group_key.group_type

    def _eval_conditions(
        self,
        *,
        group_key: FeedGroupKey,
        thresholds: FeedThresholds,
        metrics: dict,
    ) -> tuple[bool, bool, bool]:
        tick_age_p95 = _safe_float(metrics.get("tick_age_p95"))
        ws_age = _safe_float(metrics.get("ws_age"))
        spread_p95 = _safe_float(metrics.get("spread_p95"))
        depth_missing_pct = _safe_float(metrics.get("depth_missing_pct"))

        down_conditions = False
        if ws_age is not None and ws_age >= thresholds.ws_down_age_sec:
            down_conditions = True
        if tick_age_p95 is not None and tick_age_p95 > thresholds.down_age_p95:
            down_conditions = True
        if tick_age_p95 is None and ws_age is None:
            down_conditions = True

        group_type = self._group_type(group_key)
        if group_type == FeedGroupType.INDEX:
            ok_conditions = tick_age_p95 is not None and tick_age_p95 <= thresholds.ok_age_p95
            deg_conditions = tick_age_p95 is not None and tick_age_p95 <= thresholds.deg_age_p95
            return ok_conditions, deg_conditions, down_conditions

        ok_conditions = tick_age_p95 is not None and tick_age_p95 <= thresholds.ok_age_p95
        if thresholds.ok_spread_p95 is not None and spread_p95 is not None:
            ok_conditions = ok_conditions and (spread_p95 <= thresholds.ok_spread_p95)
        if thresholds.ok_depth_missing_pct is not None and depth_missing_pct is not None:
            ok_conditions = ok_conditions and (depth_missing_pct <= thresholds.ok_depth_missing_pct)

        deg_conditions = tick_age_p95 is not None and tick_age_p95 <= thresholds.deg_age_p95
        if thresholds.deg_spread_p95 is not None and spread_p95 is not None:
            deg_conditions = deg_conditions and (spread_p95 <= thresholds.deg_spread_p95)
        if thresholds.deg_depth_missing_pct is not None and depth_missing_pct is not None:
            deg_conditions = deg_conditions and (depth_missing_pct <= thresholds.deg_depth_missing_pct)
        return ok_conditions, deg_conditions, down_conditions

    def _set_since(self, flag: bool, since_ts: float | None, now_ts: float) -> float | None:
        if not flag:
            return None
        return since_ts if since_ts is not None else float(now_ts)

    def _ensure_status(
        self,
        group_key: FeedGroupKey,
        now_ts: float,
        ok_conditions: bool,
        deg_conditions: bool,
        down_conditions: bool,
    ) -> _GroupStatus:
        current = self._status_by_group.get(group_key)
        if current is not None:
            return current

        if down_conditions:
            initial_state = FeedState.DOWN
        elif ok_conditions:
            initial_state = FeedState.OK
        elif deg_conditions:
            initial_state = FeedState.DEGRADED
        else:
            initial_state = FeedState.DOWN

        status = _GroupStatus(state=initial_state, last_transition_ts=float(now_ts))
        status.ok_since = float(now_ts) if ok_conditions else None
        status.deg_since = float(now_ts) if deg_conditions else None
        status.down_since = float(now_ts) if down_conditions else None
        status.bad_ok_since = float(now_ts) if (not ok_conditions and not down_conditions) else None
        self._status_by_group[group_key] = status
        return status

    def _transition(
        self,
        *,
        group_key: FeedGroupKey,
        status: _GroupStatus,
        thresholds: FeedThresholds,
        now_ts: float,
        target_state: FeedState,
        reason: str,
    ) -> str:
        if target_state == status.state:
            return reason

        previous_state = status.state
        status.state = target_state
        status.last_transition_ts = float(now_ts)
        status.transition_times.append(float(now_ts))

        # Enforce staged recovery: DOWN -> DEGRADED -> OK must earn a fresh
        # sustained-good window while already in DEGRADED state.
        if previous_state == FeedState.DOWN and target_state == FeedState.DEGRADED:
            status.ok_since = float(now_ts)

        cutoff = float(now_ts) - float(thresholds.flap_window_sec)
        while status.transition_times and status.transition_times[0] < cutoff:
            status.transition_times.popleft()

        if len(status.transition_times) >= int(thresholds.flap_max_transitions):
            status.flap_lock_until = float(now_ts) + float(thresholds.flap_lock_sec)
            if status.state != FeedState.DOWN:
                status.state = FeedState.DEGRADED
                reason = f"{reason}|flap_lock"
        return reason

    def update_group(self, group_key: FeedGroupKey, metrics_snapshot: dict) -> dict:
        now_ts = float(self.now_fn())
        key_obj = group_key if isinstance(group_key, FeedGroupKey) else FeedGroupKey(str(group_key))
        thresholds = self._resolve_threshold(key_obj)
        metrics = dict(metrics_snapshot or {})
        if thresholds is None:
            return {
                "group": str(key_obj),
                "state": FeedState.DOWN,
                "execution_allowed": False,
                "reason": "unknown_group",
                "metrics": metrics,
                "flap_locked": False,
            }

        ok_conditions, deg_conditions, down_conditions = self._eval_conditions(
            group_key=key_obj,
            thresholds=thresholds,
            metrics=metrics,
        )
        status = self._ensure_status(
            key_obj,
            now_ts=now_ts,
            ok_conditions=ok_conditions,
            deg_conditions=deg_conditions,
            down_conditions=down_conditions,
        )

        status.ok_since = self._set_since(ok_conditions, status.ok_since, now_ts)
        status.deg_since = self._set_since(deg_conditions, status.deg_since, now_ts)
        status.down_since = self._set_since(down_conditions, status.down_since, now_ts)
        bad_ok_conditions = (not ok_conditions) and (not down_conditions)
        status.bad_ok_since = self._set_since(bad_ok_conditions, status.bad_ok_since, now_ts)

        flap_locked = (
            status.flap_lock_until is not None and now_ts < float(status.flap_lock_until)
        )
        hold_ok = _elapsed(now_ts, status.last_transition_ts) >= float(thresholds.min_hold_sec)
        reason = "hold"

        if status.state == FeedState.OK:
            if down_conditions and hold_ok and _elapsed(now_ts, status.down_since) >= float(thresholds.downgrade_window_sec):
                reason = self._transition(
                    group_key=key_obj,
                    status=status,
                    thresholds=thresholds,
                    now_ts=now_ts,
                    target_state=FeedState.DOWN,
                    reason="ok_to_down",
                )
            elif (
                bad_ok_conditions
                and hold_ok
                and _elapsed(now_ts, status.bad_ok_since) >= float(thresholds.downgrade_window_sec)
            ):
                reason = self._transition(
                    group_key=key_obj,
                    status=status,
                    thresholds=thresholds,
                    now_ts=now_ts,
                    target_state=FeedState.DEGRADED,
                    reason="ok_to_degraded",
                )
            else:
                reason = "ok_stable"

        elif status.state == FeedState.DEGRADED:
            if down_conditions and hold_ok and _elapsed(now_ts, status.down_since) >= float(thresholds.downgrade_window_sec):
                reason = self._transition(
                    group_key=key_obj,
                    status=status,
                    thresholds=thresholds,
                    now_ts=now_ts,
                    target_state=FeedState.DOWN,
                    reason="degraded_to_down",
                )
            elif ok_conditions and hold_ok and _elapsed(now_ts, status.ok_since) >= float(thresholds.upgrade_window_sec):
                if flap_locked:
                    reason = "upgrade_blocked_flap_lock"
                else:
                    reason = self._transition(
                        group_key=key_obj,
                        status=status,
                        thresholds=thresholds,
                        now_ts=now_ts,
                        target_state=FeedState.OK,
                        reason="degraded_to_ok",
                    )
            else:
                reason = "degraded_stable"

        else:  # DOWN
            down_recovery_window_sec = 30.0
            if (
                deg_conditions
                and hold_ok
                and _elapsed(now_ts, status.deg_since) >= down_recovery_window_sec
            ):
                reason = self._transition(
                    group_key=key_obj,
                    status=status,
                    thresholds=thresholds,
                    now_ts=now_ts,
                    target_state=FeedState.DEGRADED,
                    reason="down_to_degraded",
                )
            else:
                reason = "down_stable"

        flap_locked = (
            status.flap_lock_until is not None and now_ts < float(status.flap_lock_until)
        )
        return {
            "group": str(key_obj),
            "state": status.state,
            "execution_allowed": status.state == FeedState.OK,
            "reason": reason,
            "metrics": metrics,
            "flap_locked": bool(flap_locked),
        }

    def get_state(self, group_key: FeedGroupKey) -> FeedState:
        key_obj = group_key if isinstance(group_key, FeedGroupKey) else FeedGroupKey(str(group_key))
        status = self._status_by_group.get(key_obj)
        if status is not None:
            return status.state
        thresholds = self._resolve_threshold(key_obj)
        if thresholds is None:
            return FeedState.DOWN
        return FeedState.DOWN
