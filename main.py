import core.runtime_guard
from core.orchestrator import Orchestrator
from core.readiness_gate import run_readiness_check
from core.audit_log import append_event as audit_append
from core import risk_halt
from core.security_guard import enforce_startup_security
from core.instance_lock import InstanceLock
from core.session_guard import auto_clear_risk_halt_if_safe
from core.db_guard import ensure_db_ready
from core.trade_log_paths import ensure_trade_log_exists
from config import config as cfg
from pathlib import Path
import atexit

def _check_env():
    missing = []
    if not cfg.KITE_API_KEY:
        missing.append("KITE_API_KEY")
    if not cfg.KITE_API_SECRET:
        missing.append("KITE_API_SECRET")
    if cfg.ENABLE_TELEGRAM and (not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID):
        missing.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")

    if missing:
        print("[Config Warning] Missing env vars: " + ", ".join(missing))

def main():
    repo_root = Path(__file__).resolve().parent
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
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
        print(f"[DB_INIT_ERROR] {exc}")
        return
    try:
        enforce_startup_security(repo_root=repo_root, require_token=True)
    except RuntimeError as exc:
        print(str(exc))
        return
    _check_env()
    try:
        ensure_trade_log_exists()
    except Exception as exc:
        print(f"[STARTUP_WARN] trade log init failed: {exc}")
    guard_result = auto_clear_risk_halt_if_safe()
    if guard_result.get("cleared"):
        print("[SessionGuard] auto-cleared stale risk halt (market closed, no open positions).")
    elif guard_result.get("reason_code") not in {"HALT_NOT_ACTIVE", "AUTO_CLEAR_DISABLED"}:
        print(f"[SessionGuard] no clear: {guard_result.get('reason_code')}")
    live_mode = exec_mode == "LIVE"
    pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))
    if live_mode or pilot_mode:
        readiness = run_readiness_check(write_log=True)
        state = readiness.get("state", "BLOCKED")
        can_trade = bool(readiness.get("can_trade", readiness.get("ready", False)))
        if state == "BLOCKED":
            reasons = readiness.get("blockers") or readiness.get("reasons") or []
            risk_halt.set_halt("readiness_gate_fail", {"reasons": reasons})
            try:
                audit_append({
                    "event": "READINESS_FAIL",
                    "state": state,
                    "reasons": reasons,
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                })
            except Exception as exc:
                print(f"[AUDIT_ERROR] readiness_fail err={exc}")
            print(f"[Readiness] Not ready: {','.join(reasons)}")
            return
        if not can_trade:
            warnings = readiness.get("warnings") or []
            print(f"[Readiness] state={state}; can_trade={can_trade}; warnings={','.join(warnings)}")
    orchestrator = Orchestrator(total_capital=getattr(cfg, "CAPITAL", 100000), poll_interval=30)
    recon_enabled = bool(getattr(cfg, "ORDER_RECON_ENABLED", True))
    if recon_enabled:
        try:
            interval_sec = float(getattr(cfg, "ORDER_RECON_INTERVAL_SEC", 5.0))
            orchestrator.execution_router.engine.start_reconciliation_daemon(interval_sec=interval_sec)
            print(f"[RECON] reconciliation daemon started interval_sec={interval_sec}")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_start_reconciliation_daemon: {exc}")
    try:
        orchestrator.live_monitoring()
    finally:
        try:
            orchestrator.execution_router.engine.stop_reconciliation_daemon(timeout_sec=5.0)
            print("[RECON] reconciliation daemon stopped")
        except Exception as exc:
            print(f"[RECON_WARN] failed_to_stop_reconciliation_daemon: {exc}")

if __name__ == "__main__":
    main()
