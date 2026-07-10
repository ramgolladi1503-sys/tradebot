from typing import Optional
from config import config as cfg
from core.feed_state_model import FeedSnapshot, FeedVerdict, FeedLifecycleState, FeedOperationalState

# Backward-compatibility marker used by tests and runtime snapshots.
market_feed_active = True

def _get_grace_sec() -> float:
    return float(getattr(cfg, "FEED_STARTUP_GRACE_SEC", 30.0))

def _get_timeout_sec() -> float:
    return float(getattr(cfg, "FEED_NO_PROGRESS_TIMEOUT_SEC", 30.0))

def _evaluate_recovery_restart(snapshot: FeedSnapshot) -> Optional[FeedVerdict]:
    if snapshot.process_restart_required:
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.RESTART_REQUIRED,
            operational_state=FeedOperationalState.DEAD,
            feed_ok=False,
            restart_required=True,
            reason_code="PROCESS_RESTART_REQUIRED",
            blockers=["process_restart_required"],
        )

    if snapshot.feed_error_code == "AUTH_BLOCKED":
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.AUTH_BLOCKED,
            operational_state=FeedOperationalState.DEAD,
            feed_ok=False,
            restart_required=True,
            reason_code="AUTH_BLOCKED",
            blockers=["auth_blocked"],
        )

    if snapshot.recovery_blocked:
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.RECOVERY_BLOCKED,
            operational_state=FeedOperationalState.DEAD,
            feed_ok=False,
            restart_required=True,
            reason_code="RECOVERY_BLOCKED",
            blockers=["recovery_blocked"],
        )
    return None

def _evaluate_market_status(snapshot: FeedSnapshot) -> Optional[FeedVerdict]:
    if snapshot.runtime_state == "VERIFIED_HEALTHY":
        return None
    if not snapshot.market_open:
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.MARKET_CLOSED,
            operational_state=FeedOperationalState.DEAD,
            feed_ok=False,
            restart_required=False,
            reason_code="MARKET_CLOSED",
            blockers=["market_closed"],
        )
    return None

def _evaluate_startup(snapshot: FeedSnapshot, is_connected: bool, feed_ok: bool) -> Optional[FeedVerdict]:
    is_startup = snapshot.runtime_state in ("BOOTING", "STARTING", "CONNECTING", "SUBSCRIBED", "VERIFYING_OPTION_TICKS")
    if not is_startup:
        return None

    # Handle missing start_epoch (legacy compatibility condition)
    if snapshot.start_epoch is None:
        within_grace = True
        legacy_compat = True
    else:
        age = snapshot.ts_epoch - snapshot.start_epoch
        within_grace = age <= _get_grace_sec()
        legacy_compat = False

    blockers = []
    reason_code = "OK"
    if not is_connected:
        blockers.append("startup_not_connected")
        reason_code = "STARTUP_NO_WS"
    elif not feed_ok:
        blockers.append("startup_feed_not_ok")
        reason_code = "STARTUP_FEED_NOT_OK"

    if within_grace:
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.STARTING,
            operational_state=FeedOperationalState.STARTING,
            feed_ok=feed_ok,
            restart_required=False,
            reason_code=snapshot.reason_code or (reason_code if reason_code != "OK" else ("STARTING_LEGACY_COMPAT" if legacy_compat else "STARTING_GRACE")),
            blockers=blockers,
        )
    else:
        # Grace expired, but still starting means we are degraded. Not an immediate restart.
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.DEGRADED,
            operational_state=FeedOperationalState.STARTING,
            feed_ok=feed_ok,
            restart_required=False,
            reason_code=snapshot.reason_code or "STARTUP_GRACE_EXPIRED",
            blockers=blockers + ["grace_expired"],
        )

def _evaluate_recovery(snapshot: FeedSnapshot, feed_ok: bool) -> Optional[FeedVerdict]:
    if snapshot.recovery_state == "RECOVERING":
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.RECOVERING,
            operational_state=FeedOperationalState.DEGRADED,
            feed_ok=False,  # Force false when recovering
            restart_required=False,
            reason_code=snapshot.reason_code or "RECOVERING",
            blockers=["recovering"],
        )

    if snapshot.runtime_state in ("DOWN", "DEGRADED"):
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.DEGRADED,
            operational_state=FeedOperationalState.DEAD,
            feed_ok=False,  # Force false when DOWN
            restart_required=False,
            reason_code=snapshot.reason_code or "RUNTIME_DOWN",
            blockers=["runtime_down"],
        )
    return None

def _evaluate_freshness_hysteresis(snapshot: FeedSnapshot, is_connected: bool, feed_ok: bool) -> FeedVerdict:
    blockers = []
    reason_code = "OK"

    if not is_connected:
        blockers.append("not_connected")
        reason_code = "NO_WS"
    if not feed_ok:
        blockers.append("feed_not_ok")
        reason_code = "FEED_NOT_OK" if reason_code == "OK" else reason_code

    if blockers:
        return FeedVerdict(
            lifecycle_state=FeedLifecycleState.DEGRADED,
            operational_state=FeedOperationalState.DEGRADED,
            feed_ok=feed_ok,
            restart_required=False,
            reason_code=snapshot.reason_code or reason_code,
            blockers=blockers,
        )

    return FeedVerdict(
        lifecycle_state=FeedLifecycleState.LIVE,
        operational_state=FeedOperationalState.LIVE,
        feed_ok=True,
        restart_required=False,
        reason_code=snapshot.reason_code or "OK",
        blockers=[],
    )

def classify_feed_snapshot(snapshot: FeedSnapshot) -> FeedVerdict:
    # 1. Evaluate recovery & restart policy first
    verdict = _evaluate_recovery_restart(snapshot)
    if verdict is not None:
        return verdict

    # 2. Evaluate market closed status
    verdict = _evaluate_market_status(snapshot)
    if verdict is not None:
        return verdict

    # 3. WS Connectivity check logic: effective_ws_connected is operational truth source
    is_connected = snapshot.effective_ws_connected or (snapshot.runtime_state == "VERIFIED_HEALTHY")
    
    # 4. Hysteresis check
    feed_ok = snapshot.feed_ok_hysteresis_state.feed_ok or (snapshot.runtime_state == "VERIFIED_HEALTHY")

    # 5. Evaluate startup grace
    verdict = _evaluate_startup(snapshot, is_connected, feed_ok)
    if verdict is not None:
        return verdict

    # 6. Evaluate recovery / DOWN state
    verdict = _evaluate_recovery(snapshot, feed_ok)
    if verdict is not None:
        return verdict

    # 7. Fallback to normal live processing / freshness
    return _evaluate_freshness_hysteresis(snapshot, is_connected, feed_ok)
