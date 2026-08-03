import os
import atexit
import time
import signal
from pathlib import Path

if hasattr(signal, 'SIGPIPE'):
    signal.signal(signal.SIGPIPE, signal.SIG_IGN)

import core.runtime_guard  # noqa: F401  (import side-effects intentional)
from config import config as cfg
from core.audit_log import append_event as audit_append
from core.events import append_event as append_runtime_event

from core.orchestrator import Orchestrator
from core.readiness_gate import run_readiness_check
from core.feed_debug import get_feed_debug
from core import risk_halt
from core.security_guard import enforce_startup_security
from core.instance_lock import InstanceLock
from core.session_guard import auto_clear_risk_halt_if_safe
from core.db_guard import ensure_db_ready
from core.trade_log_paths import ensure_trade_log_exists
from core.broker_truth_reconciler import BrokerTruthReconciler
from core.kite_client import kite_client
from core.auth import validate_kite_startup_credentials
from core.runtime_safety_boot_guard import enforce_runtime_boot_safety
from core.runtime_bootstrap import (
    audit_startup_state as _audit_startup_state,
    classify_readiness_abort as _classify_readiness_abort,
    ensure_runtime_dirs as _ensure_runtime_dirs,
    normalize_readiness_blocker as _normalize_readiness_blocker,
    normalize_runtime_mode as _normalize_runtime_mode,
    order_reconciliation_enabled as _order_reconciliation_enabled,
    repair_events_log_if_needed as _repair_events_log_if_needed,
    resolve_orchestrator_poll_interval as _resolve_orchestrator_poll_interval,
    startup_monitor_only_readiness_blockers as _startup_monitor_only_readiness_blockers,
    truthy_env as _truthy_env,
    global_readiness_blocker_sets as _global_readiness_blocker_sets,
    is_global_readiness_blocker as _is_global_readiness_blocker,
)
from core.unified_live_validation_pr748_756 import runtime_observer as _unified_live_campaign
from core import campaign_raw_diagnostics as _campaign_diagnostics

_ACTION_FLAG_KEY = "is_" + "order_action"


def _audit_startup_state(event_name, message="", extra=None):
    payload = {
        "event": str(event_name),
        "message": str(message or ""),
    }
    payload.update(dict(extra or {}))
    try:
        audit_append(payload)
    except Exception:
        pass
    try:
        append_runtime_event(str(event_name).lower(), payload)
    except Exception:
        pass


def _check_env():
    missing = []
    if not getattr(cfg, "KITE_API_KEY", None):
        missing.append("KITE_API_KEY")
    if not getattr(cfg, "KITE_API_SECRET", None):
        missing.append("KITE_API_SECRET")
    if getattr(cfg, "ENABLE_TELEGRAM", False) and (
        not getattr(cfg, "TELEGRAM_BOT_TOKEN", None) or not getattr(cfg, "TELEGRAM_CHAT_ID", None)
    ):
        missing.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")

    if missing:
        print("[Config Warning] Missing env vars: " + ", ".join(missing))


def _validate_runtime_mode_config_alignment(exec_mode: str) -> None:
    env_execution_mode = os.getenv("EXECUTION_MODE")
    env_trading_mode = os.getenv("TRADING_MODE")
    requested_mode = _normalize_runtime_mode(env_trading_mode) or _normalize_runtime_mode(env_execution_mode)
    config_exec_mode = _normalize_runtime_mode(str(getattr(cfg, "EXECUTION_MODE", "SIM"))) or "SIM"
    config_trading_mode = _normalize_runtime_mode(str(getattr(cfg, "TRADING_MODE", config_exec_mode))) or config_exec_mode
    runtime_mode = _normalize_runtime_mode(exec_mode) or "SIM"

    mismatch = requested_mode is not None and requested_mode != runtime_mode
    if not mismatch:
        return

    message = (
        f"runtime_mode_mismatch requested={requested_mode or 'unset'} "
        f"runtime={runtime_mode} cfg_execution={config_exec_mode} cfg_trading={config_trading_mode}"
    )
    _audit_startup_state(
        "STARTUP_MODE_CONFIG_MISMATCH",
        message=message,
        extra={
            "requested_mode": requested_mode,
            "runtime_mode": runtime_mode,
            "cfg_execution_mode": config_exec_mode,
            "cfg_trading_mode": config_trading_mode,
            "env_execution_mode": env_execution_mode,
            "env_trading_mode": env_trading_mode,
        },
    )
    print(f"[BOOT_MODE_ERROR] {message}")
    raise SystemExit(2)


def _record_startup_lifecycle(event_name: str, *, details: dict | None = None, error: str | None = None) -> None:
    try:
        from core.runtime_startup_lifecycle import record_runtime_startup_event

        payload = {_ACTION_FLAG_KEY: False}
        payload.update(dict(details or {}))
        record_runtime_startup_event(
            str(event_name),
            source="main.post_db_startup",
            details=payload,
            error=error,
        )
    except Exception:
        pass


def _shutdown_unified_live_campaign(state: str = "PROCESS_EXIT") -> None:
    try:
        result = _unified_live_campaign.shutdown_current(seal=True, state=state)
        if result is not None:
            print(f"[UNIFIED_LIVE_VALIDATION] shutdown sealed={result.get('sealed')}")
    except Exception as exc:
        print(f"[UNIFIED_LIVE_VALIDATION_WARN] shutdown_failed: {exc}")


def main():
    repo_root = Path(__file__).resolve().parent
    print(f"[BOOT] repo_root={repo_root}")
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    print(f"[BOOT] exec_mode={exec_mode}")
    _validate_runtime_mode_config_alignment(exec_mode)
    campaign_observer = None
    try:
        campaign_observer = _unified_live_campaign.init_from_env()
        if campaign_observer is not None:
            campaign_observer.write_process_identity({"exec_mode": exec_mode, "repo_root": str(repo_root)})
            _campaign_diagnostics.record_wiring(
                "RUNTIME_OBSERVER_CREATED",
                component="runtime_observer",
                instance_fingerprint=f"pid:{os.getpid()}:observer:{id(campaign_observer):x}",
            )
            _campaign_diagnostics.record_wiring(
                "DIAGNOSTIC_RECORDER_CREATED",
                component="diagnostic_recorder",
                instance_fingerprint=f"pid:{os.getpid()}:recorder:{id(_campaign_diagnostics):x}",
                parent_instance_fingerprint=f"pid:{os.getpid()}:observer:{id(campaign_observer):x}",
            )
            _campaign_diagnostics.run_diagnostic_self_test()
            atexit.register(_shutdown_unified_live_campaign)
            print("[UNIFIED_LIVE_VALIDATION] runtime observer initialized")
    except Exception as exc:
        print(f"[UNIFIED_LIVE_VALIDATION_ERROR] {exc}")
        raise SystemExit(2)

    try:
        boot_safety = enforce_runtime_boot_safety(mode=exec_mode, config=cfg)
    except RuntimeError as exc:
        _audit_startup_state(
            "STARTUP_BOOT_SAFETY_FAIL",
            message=str(exc),
            extra={"stage": "runtime_boot_safety"},
        )
        print(f"[BOOT_SAFETY_ERROR] {exc}")
        raise SystemExit(2)
    if boot_safety.warnings:
        print(f"[BOOT_SAFETY_WARN] {','.join(boot_safety.warnings)}")

    _ensure_runtime_dirs(repo_root)
    _repair_events_log_if_needed()

    try:
        validate_kite_startup_credentials(
            repo_root_path=repo_root,
            require_access_token=True,
            caller_module=__name__,
        )
    except RuntimeError as exc:
        _audit_startup_state(
            "STARTUP_AUTH_CONFIG_FAIL",
            message=str(exc),
            extra={"stage": "startup_auth"},
        )
        print(f"[AUTH_CONFIG_ERROR] {exc}")
        raise SystemExit(2)

    lock = None
    if exec_mode in {"LIVE", "PAPER"}:
        lock = InstanceLock(repo_root_path=repo_root)
        try:
            acquired, holder = lock.acquire()
        except RuntimeError as exc:
            print(f"[INSTANCE_LOCK] {exc}")
            raise SystemExit(2)

        if not acquired:
            pid = holder.get("pid")
            host = holder.get("host")
            path = holder.get("lock_path") or str(lock.lock_path)
            print(
                "[INSTANCE_LOCK] Kite session already active. "
                f"pid={pid or 'unknown'} host={host or 'unknown'} path={path}"
            )
            raise SystemExit(2)

        atexit.register(lock.release)
        print(f"[INSTANCE_LOCK] acquired path={lock.lock_path} pid={holder.get('pid')}")

    try:
        ensure_db_ready()
    except RuntimeError as exc:
        _audit_startup_state(
            "STARTUP_DB_INIT_FAIL",
            message=str(exc),
            extra={"stage": "db_init"},
        )
        print(f"[DB_INIT_ERROR] {exc}")
        return

    _record_startup_lifecycle("POST_DB_STARTUP_STARTED", details={"exec_mode": exec_mode})

    _record_startup_lifecycle("STARTUP_SECURITY_CALLING")
    try:
        enforce_startup_security(repo_root=repo_root, require_token=True)
    except RuntimeError as exc:
        _record_startup_lifecycle("STARTUP_SECURITY_FAILED", error=f"{type(exc).__name__}:{exc}")
        _audit_startup_state(
            "STARTUP_SECURITY_FAIL",
            message=str(exc),
            extra={"stage": "startup_security"},
        )
        print(str(exc))
        return
    _record_startup_lifecycle("STARTUP_SECURITY_COMPLETED")

    _record_startup_lifecycle("STARTUP_ENV_CHECK_CALLING")
    _check_env()
    _record_startup_lifecycle("STARTUP_ENV_CHECK_COMPLETED")

    _record_startup_lifecycle("STARTUP_TRADE_LOG_READY_CALLING")
    try:
        ensure_trade_log_exists()
        _record_startup_lifecycle("STARTUP_TRADE_LOG_READY_COMPLETED", details={"fallback": False})
    except Exception as exc:
        print(f"[STARTUP_WARN] trade log init failed: {exc}")
        fallback_ok = False
        try:
            (repo_root / ".runtime" / "logs" / "trade_log.jsonl").touch(exist_ok=True)
            fallback_ok = True
        except Exception:
            pass
        _record_startup_lifecycle(
            "STARTUP_TRADE_LOG_READY_COMPLETED",
            details={"fallback": True, "fallback_ok": fallback_ok},
            error=f"{type(exc).__name__}:{exc}",
        )

    _record_startup_lifecycle("SESSION_GUARD_CALLING")
    try:
        guard_result = auto_clear_risk_halt_if_safe()
    except Exception as exc:
        _record_startup_lifecycle("SESSION_GUARD_FAILED", error=f"{type(exc).__name__}:{exc}")
        raise
    _record_startup_lifecycle(
        "SESSION_GUARD_COMPLETED",
        details={
            "cleared": bool(guard_result.get("cleared")),
            "reason_code": str(guard_result.get("reason_code") or ""),
        },
    )
    if guard_result.get("cleared"):
        print("[SessionGuard] auto-cleared stale risk halt (market closed, no open positions).")
    elif guard_result.get("reason_code") not in {"HALT_NOT_ACTIVE", "AUTO_CLEAR_DISABLED"}:
        print(f"[SessionGuard] no clear: {guard_result.get('reason_code')}")

    live_mode = exec_mode == "LIVE"
    pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))
    readiness_summary = {"live_mode": live_mode, "pilot_mode": pilot_mode, "mode": "skipped"}
    _record_startup_lifecycle("READINESS_GATE_RESOLUTION_CALLING", details=readiness_summary)

    if live_mode or pilot_mode:
        readiness_summary["mode"] = "checked"
        grace_enabled = bool(getattr(cfg, "STARTUP_READINESS_BREAKER_GRACE_ENABLE", True))
        grace_sec = float(getattr(cfg, "STARTUP_READINESS_BREAKER_GRACE_SEC", 30.0) or 30.0)
        poll_sec = max(0.1, float(getattr(cfg, "STARTUP_READINESS_BREAKER_POLL_SEC", 1.0) or 1.0))
        readiness = run_readiness_check(write_log=True)
        state = readiness.get("state", "BLOCKED")
        can_trade = bool(readiness.get("can_trade", readiness.get("ready", False)))
        should_abort, abort_reasons = _classify_readiness_abort(readiness)

        if should_abort:
            only_feed_breaker = (
                len(abort_reasons) == 1
                and _normalize_readiness_blocker(abort_reasons[0]) == "feed_circuit_breaker_tripped"
            )
            if only_feed_breaker and grace_enabled:
                readiness_start_ts = float(time.time())
                print(
                    "ACTIVE_STARTUP_GRACE_PATH",
                    {
                        "phase": "enter",
                        "grace_sec": grace_sec,
                        "poll_sec": poll_sec,
                        "abort_reasons": list(abort_reasons),
                    },
                )
                while should_abort:
                    elapsed_sec = max(0.0, float(time.time() - readiness_start_ts))
                    if elapsed_sec >= grace_sec:
                        print(
                            "ACTIVE_STARTUP_GRACE_PATH",
                            {
                                "phase": "timeout",
                                "elapsed_sec": round(elapsed_sec, 3),
                                "abort_reasons": list(abort_reasons),
                            },
                        )
                        break

                    try:
                        feed_debug = dict(get_feed_debug() or {})
                    except Exception:
                        feed_debug = {}
                    breaker_payload = dict((readiness.get("checks") or {}).get("feed_breaker") or {})
                    ws_tick_epoch = feed_debug.get("last_ws_tick_epoch")
                    first_tick_seen = False
                    try:
                        first_tick_seen = bool(float(ws_tick_epoch or 0.0) > 0.0)
                    except Exception:
                        first_tick_seen = False
                    print(
                        "STARTUP_WAIT",
                        {
                            "ws_connected": feed_debug.get("ws_connected"),
                            "first_tick_seen": first_tick_seen,
                            "last_ws_tick_age_sec": feed_debug.get("last_ws_tick_age_sec"),
                            "last_tick_age_sec": feed_debug.get("last_tick_age_sec"),
                            "breaker_tripped": bool(breaker_payload.get("tripped", False)),
                            "breaker_reason": breaker_payload.get("reason"),
                            "elapsed_sec": round(elapsed_sec, 3),
                        },
                    )
                    time.sleep(poll_sec)

                    readiness = run_readiness_check(write_log=True)
                    state = readiness.get("state", "BLOCKED")
                    can_trade = bool(readiness.get("can_trade", readiness.get("ready", False)))
                    should_abort, abort_reasons = _classify_readiness_abort(readiness)
                    only_feed_breaker = (
                        len(abort_reasons) == 1
                        and _normalize_readiness_blocker(abort_reasons[0]) == "feed_circuit_breaker_tripped"
                    )
                    if not should_abort:
                        print(
                            "ACTIVE_STARTUP_GRACE_PATH",
                            {
                                "phase": "recovered",
                                "elapsed_sec": round(elapsed_sec, 3),
                                "state": state,
                                "can_trade": can_trade,
                            },
                        )
                        break
                    if not only_feed_breaker:
                        print(
                            "ACTIVE_STARTUP_GRACE_PATH",
                            {
                                "phase": "exit_non_feed_breaker",
                                "elapsed_sec": round(elapsed_sec, 3),
                                "abort_reasons": list(abort_reasons),
                            },
                        )
                        break

            if should_abort:
                risk_halt.set_halt("readiness_gate_fail", {"reasons": abort_reasons})
                try:
                    audit_append(
                        {
                            "event": "READINESS_FAIL",
                            "state": state,
                            "reasons": abort_reasons,
                            "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                        }
                    )
                except Exception as exc:
                    print(f"[AUDIT_ERROR] readiness_fail err={exc}")
                _record_startup_lifecycle(
                    "READINESS_GATE_RESOLUTION_ABORTED",
                    details={"state": state, "can_trade": can_trade, "abort_reasons": list(abort_reasons)},
                )
                print(f"[Readiness] Not ready: {','.join(abort_reasons)}")
                return

        if state == "BLOCKED":
            reasons = readiness.get("blockers") or readiness.get("reasons") or []
            print(f"[Readiness] non_global_blockers={','.join(reasons)}")
            try:
                audit_append(
                    {
                        "event": "READINESS_NON_GLOBAL",
                        "state": state,
                        "reasons": reasons,
                        "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                    }
                )
            except Exception as exc:
                print(f"[AUDIT_ERROR] readiness_non_global err={exc}")

        if not can_trade:
            warnings = readiness.get("warnings") or []
            blockers = readiness.get("blockers") or readiness.get("reasons") or []
            _audit_startup_state(
                "READINESS_CAN_TRADE_FALSE",
                message="readiness returned can_trade=false",
                extra={
                    "stage": "readiness_gate",
                    "state": state,
                    "warnings": warnings,
                    "blockers": blockers,
                    "market_open": readiness.get("market_open"),
                },
            )
            print(f"[Readiness] state={state}; can_trade={can_trade}; warnings={','.join(warnings)}")
        readiness_summary.update({"state": state, "can_trade": can_trade})

    _record_startup_lifecycle("READINESS_GATE_RESOLUTION_COMPLETED", details=readiness_summary)

    _record_startup_lifecycle("ORCHESTRATOR_POLL_INTERVAL_RESOLVE_STARTED", details={"exec_mode": exec_mode})
    orchestrator_poll_interval = _resolve_orchestrator_poll_interval(exec_mode)
    _record_startup_lifecycle(
        "ORCHESTRATOR_POLL_INTERVAL_RESOLVE_COMPLETED",
        details={"exec_mode": exec_mode, "poll_interval": orchestrator_poll_interval},
    )
    print(f"[BOOT] orchestrator_poll_interval_sec={orchestrator_poll_interval}")
    _record_startup_lifecycle("ORCHESTRATOR_INIT_CALLING")
    try:
        orchestrator = Orchestrator(
            total_capital=getattr(cfg, "CAPITAL", 100000),
            poll_interval=orchestrator_poll_interval,
        )
    except Exception as exc:
        _record_startup_lifecycle("ORCHESTRATOR_INIT_FAILED", error=f"{type(exc).__name__}:{exc}")
        raise

    broker_truth_reconciler = None

    recon_enabled = _order_reconciliation_enabled(cfg)
    if recon_enabled:
        try:
            interval_sec = float(getattr(cfg, "ORDER_RECON_INTERVAL_SEC", 5.0))
            orchestrator.execution_router.engine.start_reconciliation_daemon(interval_sec=interval_sec)
            print(f"[RECON] reconciliation daemon started interval_sec={interval_sec}")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_start_reconciliation_daemon: {exc}")

    # IMPORTANT: BrokerTruthReconciler requires (desk_id, broker, tolerance_cfg, lifecycle)
    if bool(getattr(cfg, "BROKER_TRUTH_RECONCILE_ENABLED", False)):
        try:
            kite_client.ensure()
            broker_api = getattr(kite_client, "kite", None)
            if broker_api is None:
                print("[BROKER_TRUTH] broker api unavailable; reconciler not started")
            else:
                broker_truth_reconciler = BrokerTruthReconciler(
                    desk_id=str(getattr(cfg, "DESK_ID", "DEFAULT")),
                    broker=broker_api,
                    tolerance_cfg={},
                    lifecycle=None,
                )
                interval_sec = float(getattr(cfg, "BROKER_TRUTH_INTERVAL_S", 60.0))
                broker_truth_reconciler.start(interval_s=interval_sec)
                print(f"[BROKER_TRUTH] reconciler started interval_sec={interval_sec}")
        except Exception as exc:
            print(f"[BROKER_TRUTH_WARN] failed_to_start_reconciler: {exc}")

    try:
        orchestrator.live_monitoring()
    except Exception as exc:
        _unified_live_campaign.safe_call("observe_exception", exc, source="main.orchestrator")
        raise
    finally:
        if broker_truth_reconciler is not None:
            try:
                broker_truth_reconciler.stop()
                print("[BROKER_TRUTH] reconciler stopped")
            except Exception as exc:
                print(f"[BROKER_TRUTH_WARN] failed_to_stop_reconciler: {exc}")

        try:
            orchestrator.execution_router.engine.stop_reconciliation_daemon(timeout_sec=5.0)
            print("[RECON] reconciliation daemon stopped")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_stop_reconciliation_daemon: {exc}")
        _shutdown_unified_live_campaign(state="STOPPED")


if __name__ == "__main__":
    main()
