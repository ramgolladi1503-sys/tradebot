"""Runtime health snapshot helper.

Produces a compact JSON snapshot for operator dashboards and CLI checks.
"""

from __future__ import annotations

from core.paths import data_root, logs_dir
import json
from pathlib import Path
from typing import Any

from config import config as cfg
from core.feed_debug import get_feed_debug
from core.feed_recovery_runtime import classify_feed_recovery_runtime
from core.feed_zombie_state import classify_feed_zombie_state
from core.freshness_sla import get_freshness_status
from core.runtime_truth_integrity import build_truth_integrity_alerts, truth_hash_from_mapping
from core.time_utils import is_market_open_ist, now_utc_epoch
from core.runtime_boot_identity import stamp_runtime_payload
from core.paths import runtime_dir
from core.events import append_event


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    tmp.replace(path)


def _safe_json_payload(path: Path) -> dict[str, Any]:
    try:
        if not path.exists():
            return {}
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _first_non_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def get_runtime_health(orchestrator: Any | None = None, now_epoch: float | None = None) -> dict[str, Any]:
    ts_epoch = float(now_epoch if now_epoch is not None else now_utc_epoch())
    freshness = dict(get_freshness_status(force=False) or {})
    feed_debug = dict(get_feed_debug(now_epoch=ts_epoch) or {})
    # The feed writer's authoritative latest artifact lives under the shared
    # runtime logs root. Reading runtime_dir()/feed_runtime_latest.json would
    # select a different, usually absent, path and recreate the dual-path race.
    feed_runtime_path = logs_dir() / "feed_runtime_latest.json"
    feed_runtime_payload = _safe_json_payload(feed_runtime_path)

    market_open = bool(freshness.get("market_open", is_market_open_ist()))
    mode = str(
        freshness.get("mode")
        or freshness.get("execution_mode")
        or getattr(cfg, "EXECUTION_MODE", "SIM")
    ).upper()
    raw_sla_status = str(freshness.get("state") or "").upper()
    sla_state = "LIVE" if (market_open and not bool(freshness.get("allow_stale_quotes", False))) else "PLANNING"

    ltp_age = None
    depth_age = None
    ltp_block = freshness.get("ltp") or {}
    depth_block = freshness.get("depth") or {}
    allow_stale_quotes = bool(freshness.get("allow_stale_quotes", False))
    ltp_required = bool(market_open and (not allow_stale_quotes))
    depth_required = bool(market_open and bool((depth_block or {}).get("required", False)))
    ltp_max_age_sec = None
    depth_max_age_sec = None
    if isinstance(ltp_block, dict):
        ltp_age = ltp_block.get("age_sec")
        if "required" in ltp_block:
            ltp_required = bool(ltp_block.get("required"))
        ltp_max_age_sec = ltp_block.get("max_age_sec")
    if isinstance(depth_block, dict):
        depth_age = depth_block.get("age_sec")
        if "required" in depth_block:
            depth_required = bool(depth_block.get("required"))
        depth_max_age_sec = depth_block.get("max_age_sec")

    feed = {
        "ws_connected": feed_debug.get("ws_connected"),
        "subscriptions_count": feed_debug.get("subscribed_tokens_count"),
        "subscribed_tokens_count": feed_debug.get("subscribed_tokens_count"),
        "intended_tokens_count": feed_debug.get("intended_tokens_count"),
        "missing_option_tokens_count": feed_debug.get("missing_option_tokens_count"),
        "subscribed_option_tokens_count": feed_debug.get("subscribed_option_tokens_count"),
        "option_ticks_verified": feed_debug.get("option_ticks_verified"),
        "feed_ok": _first_non_none(feed_runtime_payload.get("feed_ok"), feed_debug.get("feed_ok")),
        "execution_feed_ready": _first_non_none(
            feed_runtime_payload.get("execution_feed_ready"),
            feed_debug.get("execution_feed_ready"),
        ),
        "runtime_state": feed_debug.get("feed_runtime_state"),
        "last_error": feed_debug.get("feed_runtime_last_error"),
        "last_tick_age_sec": feed_debug.get("last_tick_age_sec"),
        "ltp_age_sec": ltp_age,
        "depth_age_sec": depth_age,
        "allow_stale_quotes": allow_stale_quotes,
        "ltp_required": bool(ltp_required),
        "ltp_max_age_sec": ltp_max_age_sec,
        "depth_required": bool(depth_required),
        "depth_max_age_sec": depth_max_age_sec,
        "transport_state": feed_debug.get("transport_state"),
        "transport_reason": feed_debug.get("transport_reason"),
        "transport_healthy": feed_debug.get("transport_healthy"),
        "feed_truth_state": _first_non_none(feed_debug.get("feed_truth_state"), feed_runtime_payload.get("feed_truth_state")),
        "feed_truth_reason_code": _first_non_none(feed_debug.get("feed_truth_reason_code"), feed_runtime_payload.get("feed_truth_reason_code")),
        # The persisted feed_runtime_latest artifact is the authoritative
        # snapshot. In-memory feed_debug may lag one atomic write behind;
        # preferring its hash creates false mismatch alerts against the
        # current persisted payload.
        "snapshot_hash": _first_non_none(feed_runtime_payload.get("snapshot_hash"), feed_debug.get("snapshot_hash")),
        "snapshot_hash_version": _first_non_none(feed_runtime_payload.get("snapshot_hash_version"), feed_debug.get("snapshot_hash_version")),
        "transport_heartbeat_epoch": _first_non_none(feed_runtime_payload.get("transport_heartbeat_epoch"), feed_debug.get("transport_heartbeat_epoch")),
        "transport_heartbeat_age_sec": _first_non_none(feed_runtime_payload.get("transport_heartbeat_age_sec"), feed_debug.get("transport_heartbeat_age_sec")),
        "transport_heartbeat_state": _first_non_none(feed_runtime_payload.get("transport_heartbeat_state"), feed_debug.get("transport_heartbeat_state")),
        "sla_state": sla_state,
        "sla_status": raw_sla_status or freshness.get("state"),
        "reasons": list(freshness.get("reasons") or []),
    }
    # Only the persisted feed snapshot is authoritative for integrity. During
    # startup or atomic replacement it may be absent/empty while feed_debug
    # still contains an in-memory hash from a different state.
    authoritative_snapshot_available = bool(feed_runtime_payload)
    expected_snapshot_hash = ""
    integrity_alerts: list[dict[str, Any]] = []
    has_integrity_evidence = authoritative_snapshot_available
    if has_integrity_evidence:
        expected_snapshot_hash = truth_hash_from_mapping(
            feed_runtime_payload,
            exclude_keys=(
                "snapshot_hash",
                "snapshot_hash_version",
                "transport_heartbeat",
                "transport_heartbeat_epoch",
                "transport_heartbeat_age_sec",
                "transport_heartbeat_source",
                "transport_heartbeat_state",
                "transport_heartbeat_reason",
                "truth_integrity_alerts",
                "truth_integrity_alert_count",
                "truth_integrity_status",
            ),
        )
        integrity_alerts = build_truth_integrity_alerts(
            transport_state=feed.get("transport_state"),
            feed_truth_state=feed.get("feed_truth_state"),
            snapshot_hash=feed.get("snapshot_hash"),
            expected_snapshot_hash=expected_snapshot_hash,
        )
    if not authoritative_snapshot_available:
        feed["snapshot_hash"] = None
    feed["snapshot_hash_expected"] = expected_snapshot_hash or None
    feed["snapshot_hash_match"] = bool(
        feed.get("snapshot_hash")
        and expected_snapshot_hash
        and str(feed.get("snapshot_hash")) == str(expected_snapshot_hash)
    )
    feed["truth_integrity_alerts"] = integrity_alerts
    feed["truth_integrity_alert_count"] = len(integrity_alerts)
    feed["truth_integrity_status"] = "ALERT" if integrity_alerts else "OK"
    warmup_clean_cycles = feed_debug.get("warmup_clean_cycles")
    warmup_required_clean_cycles = feed_debug.get("warmup_required_clean_cycles")
    # The orchestrator owns the consecutive clean-cycle counter. Preserve
    # missing-proof fail-closed behavior when no owner is supplied, while
    # publishing the current owner state for the recovery proof reader.
    if orchestrator is not None:
        owner_cycles = getattr(orchestrator, "_pilot_unlock_clean_cycles", None)
        if isinstance(owner_cycles, int) and owner_cycles >= 0:
            warmup_clean_cycles = owner_cycles
            configured_required = getattr(cfg, "PAPER_PILOT_UNLOCK_CLEAN_CYCLES", None)
            if isinstance(configured_required, int) and configured_required > 0:
                warmup_required_clean_cycles = configured_required
    feed["warmup_clean_cycles"] = warmup_clean_cycles
    feed["warmup_required_clean_cycles"] = warmup_required_clean_cycles
    recovery_runtime = classify_feed_recovery_runtime(feed)
    feed["recovery_runtime"] = recovery_runtime.to_payload()
    feed["full_feed_proof_ready"] = bool(recovery_runtime.context.get("full_feed_proof_ready"))
    feed["full_feed_proof_blockers"] = list(recovery_runtime.context.get("full_feed_proof_blockers") or [])
    feed["latest_option_tick_ts"] = feed_debug.get("last_ws_tick_epoch")
    feed["latest_option_tick_age_sec"] = feed_debug.get("last_ws_tick_age_sec")
    feed["underlying_ltp_age_sec"] = feed_debug.get("last_tick_age_sec")
    feed["underlying_ltp_stale_symbols"] = list(
        symbol
        for symbol, age in dict(feed_debug.get("option_last_tick_age_by_symbol") or {}).items()
        if age is None
        or (float(age) if age is not None else 0.0) > float(getattr(cfg, "FEED_HEALTH_MAX_LTP_AGE_SEC", 2.5))
    )
    feed["underlying_ltp_age_by_symbol"] = dict(feed_debug.get("option_last_tick_age_by_symbol") or {})
    feed["underlying_ltp_proof_state"] = "FULL" if bool(recovery_runtime.context.get("full_feed_proof_ready")) else "STALE"
    feed["depth_proof_state"] = "FULL" if bool(feed_debug.get("last_depth_age_sec") is not None and float(feed_debug.get("last_depth_age_sec")) <= float(getattr(cfg, "FEED_HEALTH_MAX_DEPTH_AGE_SEC", 6.0))) else "STALE"
    feed["recovery_generation_id"] = feed_debug.get("recovery_generation_id")
    feed["last_recovery_generation_id"] = feed_debug.get("last_recovery_generation_id")
    feed["subscription_generation_id"] = feed_debug.get("subscription_generation_id")
    feed["last_subscription_generation_id"] = feed_debug.get("last_subscription_generation_id")
    blockers = list(feed.get("reasons") or [])
    if feed.get("runtime_state") in {"IMPORT_MISSING", "AUTH_BLOCKED", "SUBSCRIBE_FAILED", "RECOVERY_BLOCKED"}:
        blockers.append(f"ws_runtime:{feed.get('runtime_state')}")
    reconnect_blocked_reason = str(feed_debug.get("reconnect_blocked_reason") or "").strip().lower()
    if reconnect_blocked_reason:
        blockers.append(f"ws_reconnect_blocked:{reconnect_blocked_reason}")
    if feed.get("last_error"):
        blockers.append(f"ws_error:{feed.get('last_error')}")

    feed_zombie = classify_feed_zombie_state(
        feed,
        market_open=market_open,
        mode=mode,
        require_live_feed=bool(market_open and not allow_stale_quotes),
    )
    if feed_zombie.is_zombie:
        feed["runtime_state"] = feed_zombie.state
        for blocker in feed_zombie.blockers:
            if blocker not in blockers:
                blockers.append(blocker)
    if integrity_alerts:
        for alert in integrity_alerts:
            blocker_code = f"truth_integrity:{str(alert.get('code') or 'ALERT')}"
            if blocker_code not in blockers:
                blockers.append(blocker_code)
        try:
            append_event(
                "runtime_truth_integrity_alert",
                {
                    "read_only": True,
                    "is_order_action": False,
                    "broker_api_called": False,
                    "transport_state": feed.get("transport_state"),
                    "feed_truth_state": feed.get("feed_truth_state"),
                    "snapshot_hash": feed.get("snapshot_hash"),
                    "snapshot_hash_expected": expected_snapshot_hash or None,
                    "alerts": integrity_alerts,
                    "alert_count": len(integrity_alerts),
                },
            )
        except Exception:
            pass
    feed["feed_zombie"] = feed_zombie.to_payload()
    feed["blockers"] = blockers

    execution_engine = getattr(orchestrator, "execution_engine", None)
    kill_switch_triggered = None
    kill_switch_reason = None
    last_spread_decision = None
    recon = {"daemon_running": None, "last_cycle_ts_epoch": None}
    if execution_engine is not None:
        kill_switch_triggered = getattr(execution_engine, "kill_switch_triggered", None)
        kill_switch_reason = getattr(execution_engine, "kill_switch_reason", None)
        try:
            last_spread_decision = execution_engine.get_last_spread_decision()
        except Exception:
            last_spread_decision = None
        try:
            recon = execution_engine.get_reconciliation_status()
        except Exception:
            recon = {"daemon_running": None, "last_cycle_ts_epoch": None}

    risk_state = getattr(orchestrator, "risk_state", None)
    risk = {
        "hard_halt": None,
        "daily_pnl_pct": None,
        "open_risk_pct": None,
    }
    if risk_state is not None:
        try:
            risk["hard_halt"] = bool(getattr(risk_state, "mode", "") == "HARD_HALT")
        except Exception:
            risk["hard_halt"] = None
        try:
            risk["daily_pnl_pct"] = float(getattr(risk_state, "daily_pnl_pct", 0.0))
        except Exception:
            risk["daily_pnl_pct"] = None
        try:
            risk["open_risk_pct"] = float(getattr(risk_state, "open_risk_pct", 0.0))
        except Exception:
            risk["open_risk_pct"] = None

    execution = {
        "kill_switch_triggered": kill_switch_triggered,
        "kill_switch_reason": kill_switch_reason,
        "last_spread_decision": last_spread_decision,
    }
    try:
        decision_breakers = getattr(orchestrator, "decision_breakers", None)
        if decision_breakers is not None:
            execution["decision_breakers"] = decision_breakers.snapshot(now_ts=ts_epoch)
    except Exception:
        execution["decision_breakers"] = {"error": "decision_breakers_snapshot_failed"}

    return {
        "ts_epoch": ts_epoch,
        "snapshot_ts_epoch": ts_epoch,
        "snapshot_age_sec": 0.0,
        "mode": mode,
        "market_open": market_open,
        "feed": feed,
        "execution": execution,
        "risk": risk,
        "recon": recon,
    }


def write_runtime_health_snapshot(orchestrator: Any | None = None, path: str | Path | None = None) -> dict[str, Any]:
    payload = get_runtime_health(orchestrator=orchestrator)
    payload = stamp_runtime_payload(
        payload,
        writer="runtime_health",
    )
    target = Path(path or getattr(cfg, "RUNTIME_HEALTH_PATH", str(logs_dir() / "runtime_health_latest.json")))
    _atomic_write(target, payload)
    return payload
