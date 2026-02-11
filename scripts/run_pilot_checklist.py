import sys
import json
import argparse
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg
from core import model_registry
from core.time_utils import now_ist, is_market_open_ist


def _check_risk_profile():
    if not getattr(cfg, "LIVE_PILOT_MODE", False):
        return True, []
    if getattr(cfg, "RISK_PROFILE", "PILOT") != "PILOT":
        return False, ["risk_profile_not_pilot"]
    return True, []


def _check_whitelist():
    if not getattr(cfg, "LIVE_PILOT_MODE", False):
        return True, []
    wl = getattr(cfg, "LIVE_STRATEGY_WHITELIST", [])
    if not wl:
        return False, ["strategy_whitelist_empty"]
    perf_path = Path("logs/strategy_perf.json")
    if not perf_path.exists():
        return False, ["strategy_registry_missing"]
    try:
        stats = json.loads(perf_path.read_text())
        known = set(stats.keys())
    except Exception:
        return False, ["strategy_registry_unreadable"]
    missing = [s for s in wl if s not in known]
    if missing:
        return False, [f"strategy_whitelist_unknown:{','.join(missing)}"]
    return True, []


def _check_audit_files():
    if not getattr(cfg, "AUDIT_REQUIRED_TO_TRADE", True):
        return True, []
    day = (now_ist() - timedelta(days=1)).date().isoformat()
    audit_path = Path(f"logs/daily_audit_{day}.json")
    exec_path = Path(f"logs/execution_report_{day}.json")
    missing = []
    if not audit_path.exists():
        missing.append(audit_path.name)
    if not exec_path.exists():
        missing.append(exec_path.name)
    if missing:
        return False, [f"audit_missing:{','.join(missing)}"]
    return True, []


def _check_feed():
    from core.freshness_sla import get_freshness_status
    data = get_freshness_status(force=False)
    max_age = float(getattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5))
    max_depth_age = float(getattr(cfg, "SLA_MAX_DEPTH_AGE_SEC", 2.0))
    market_open = bool(data.get("market_open", is_market_open_ist()))
    depth_lag = (data.get("depth") or {}).get("age_sec")
    tick_lag = (data.get("ltp") or {}).get("age_sec")
    if not market_open:
        return True, []
    if depth_lag is None:
        return False, ["depth_feed_stale"]
    if depth_lag > max_depth_age:
        return False, ["depth_feed_stale"]
    if tick_lag is None:
        return False, ["tick_feed_stale"]
    if tick_lag > max_age:
        return False, ["tick_feed_stale"]
    return True, []


def _check_models():
    active = {
        "xgb": model_registry.get_active("xgb"),
        "deep": model_registry.get_active("deep"),
        "micro": model_registry.get_active("micro"),
        "ensemble": model_registry.get_active("ensemble"),
    }
    if not any(active.values()):
        return False, ["model_registry_empty"]
    return True, []


def run_checks():
    results = []
    for fn in (_check_risk_profile, _check_whitelist, _check_audit_files, _check_feed, _check_models):
        ok, reasons = fn()
        results.append((ok, reasons))
    ok = all(r[0] for r in results)
    reasons = []
    for r in results:
        if not r[0]:
            reasons.extend(r[1])
    return ok, reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Print status without exiting non-zero.")
    args = parser.parse_args()
    ok, reasons = run_checks()
    status = "PASS" if ok else "FAIL"
    print(f"Pilot checklist: {status}")
    if reasons:
        print("Reasons:")
        for r in reasons:
            print(f"- {r}")
    if args.dry_run:
        return
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
