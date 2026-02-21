from core.orchestrator import Orchestrator
from core.readiness_gate import run_readiness_check
from core.audit_log import append_event as audit_append
from core import risk_halt
from core.security_guard import enforce_startup_security
from core.session_guard import auto_clear_risk_halt_if_safe
from core.db_guard import ensure_db_ready
from core.trade_log_paths import ensure_trade_log_exists
from config import config as cfg
from pathlib import Path

def _check_env():
    missing = []
    if not cfg.KITE_API_KEY:
        missing.append("KITE_API_KEY")
    if not cfg.KITE_API_SECRET:
        missing.append("KITE_API_SECRET")
    if not cfg.KITE_ACCESS_TOKEN:
        missing.append("KITE_ACCESS_TOKEN")
    if cfg.ENABLE_TELEGRAM and (not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID):
        missing.append("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID")

    if missing:
        print("[Config Warning] Missing env vars: " + ", ".join(missing))

def main():
    repo_root = Path(__file__).resolve().parent
    try:
        ensure_db_ready()
    except RuntimeError as exc:
        print(f"[DB_INIT_ERROR] {exc}")
        return
    try:
        token = enforce_startup_security(repo_root=repo_root, require_token=True)
    except RuntimeError as exc:
        print(str(exc))
        return
    if token:
        cfg.KITE_ACCESS_TOKEN = token
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
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
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
    orchestrator.live_monitoring()

if __name__ == "__main__":
    main()
