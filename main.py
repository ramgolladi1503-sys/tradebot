from core.orchestrator import Orchestrator
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
    orchestrator = Orchestrator(total_capital=getattr(cfg, "CAPITAL", 100000), poll_interval=30)
    orchestrator.live_monitoring()

if __name__ == "__main__":
    main()
