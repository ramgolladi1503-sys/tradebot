import argparse
import json
from pathlib import Path
from datetime import datetime

from config import config as cfg
from core.strategy_lifecycle import StrategyLifecycle, STATES


def _latest_file(pattern: str):
    files = sorted(Path("logs").glob(pattern))
    return files[-1] if files else None


def _load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _check_backtest(strategy_id: str):
    if not getattr(cfg, "PROMOTION_REQUIRE_BACKTEST", True):
        return True, "backtest_not_required"
    path = Path("logs/strategy_perf.json")
    if not path.exists():
        return False, "strategy_perf_missing"
    data = _load_json(path) or {}
    entry = data.get(strategy_id)
    if not entry:
        return False, "strategy_not_in_perf"
    pf = entry.get("profit_factor")
    win_rate = entry.get("win_rate") or entry.get("winrate")
    try:
        pf_val = float(pf)
    except Exception:
        pf_val = 0.0
    try:
        win_val = float(win_rate)
    except Exception:
        win_val = 0.0
    if pf_val < getattr(cfg, "WF_MIN_PF", 1.2):
        return False, "profit_factor_below_gate"
    if win_val < getattr(cfg, "WF_MIN_WIN_RATE", 0.45):
        return False, "win_rate_below_gate"
    return True, "backtest_ok"


def _check_stress():
    if not getattr(cfg, "PROMOTION_REQUIRE_STRESS", True):
        return True, "stress_not_required"
    path = _latest_file("stress_report_*.json")
    if not path:
        return False, "stress_report_missing"
    report = _load_json(path) or {}
    failures = report.get("failure_modes") or []
    if failures:
        return False, "stress_failures"
    return True, "stress_ok"


def _check_pilot_days(required_days: int):
    files = sorted(Path("logs").glob("daily_audit_*.json"))
    if len(files) < required_days:
        return False, "insufficient_daily_audits"
    recent = files[-required_days:]
    for f in recent:
        report = _load_json(f) or {}
        dq = report.get("data_quality_failures") or []
        if dq:
            return False, "data_quality_failures"
    return True, "pilot_days_ok"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--to", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target = args.to.upper()
    if target not in STATES:
        raise SystemExit(f"Invalid target state: {target}")

    lifecycle = StrategyLifecycle()
    strategy_id = args.strategy

    gates = []
    ok, reason = _check_backtest(strategy_id)
    gates.append((ok, reason))
    ok, reason = _check_stress()
    gates.append((ok, reason))
    if target in ("PILOT", "LIVE"):
        ok, reason = _check_pilot_days(getattr(cfg, "PROMOTION_PILOT_DAYS_REQUIRED", 3))
        gates.append((ok, reason))

    if not all(x[0] for x in gates):
        print("Promotion: FAIL")
        for passed, reason in gates:
            if not passed:
                print(f"- {reason}")
        raise SystemExit(1)

    if args.dry_run:
        print("Promotion: DRY-RUN")
        print(f"strategy={strategy_id} -> {target}")
        for passed, reason in gates:
            if passed:
                print(f"- {reason}")
        return

    lifecycle.set_state(strategy_id, target, reason="manual_promotion", meta={"ts": datetime.utcnow().isoformat()})
    print("Promotion: OK")
    print(f"strategy={strategy_id} -> {target}")


if __name__ == "__main__":
    main()
