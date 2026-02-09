from core.orchestrator import Orchestrator
from core.readiness_gate import run_readiness_check
from core.audit_log import append_event as audit_append
from core import risk_halt
from config import config as cfg

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
    _check_env()
    exec_mode = str(getattr(cfg, "EXECUTION_MODE", "SIM")).upper()
    live_mode = exec_mode == "LIVE"
    pilot_mode = bool(getattr(cfg, "LIVE_PILOT_MODE", False))
    if live_mode or pilot_mode:
        readiness = run_readiness_check(write_log=True)
        if not readiness.get("ready"):
            reasons = readiness.get("reasons") or []
            risk_halt.set_halt("readiness_gate_fail", {"reasons": reasons})
            try:
                audit_append({
                    "event": "READINESS_FAIL",
                    "reasons": reasons,
                    "desk_id": getattr(cfg, "DESK_ID", "DEFAULT"),
                })
            except Exception as exc:
                print(f"[AUDIT_ERROR] readiness_fail err={exc}")
            print(f"[Readiness] Not ready: {','.join(reasons)}")
            return
    orchestrator = Orchestrator(total_capital=getattr(cfg, "CAPITAL", 100000), poll_interval=30)
    orchestrator.live_monitoring()

if __name__ == "__main__":
    main()
