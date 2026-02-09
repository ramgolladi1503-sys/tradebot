import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import config as cfg

DECISION_JSONL = Path(getattr(cfg, "DECISION_LOG_PATH", str(ROOT / "logs" / "decision_events.jsonl")))
REPORT_PATH = ROOT / "logs" / "rl_shadow_report.json"


def _parse_ts(ts):
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def load_decision_events(path: Path):
    if not path.exists():
        return []
    out = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def build_report(events):
    by_day = {}
    for ev in events:
        mult = ev.get("action_size_multiplier")
        pnl = ev.get("pnl_horizon_15m")
        ts = _parse_ts(ev.get("ts", ""))
        if ts is None or mult is None or pnl is None:
            continue
        day = ts.strftime("%Y-%m-%d")
        rec = by_day.setdefault(day, {
            "count": 0,
            "baseline_pnl": 0.0,
            "rl_pnl": 0.0,
            "avg_multiplier": 0.0,
            "changed_count": 0,
        })
        rec["count"] += 1
        rec["baseline_pnl"] += float(pnl)
        rec["rl_pnl"] += float(pnl) * float(mult)
        rec["avg_multiplier"] += float(mult)
        if float(mult) != 1.0:
            rec["changed_count"] += 1

    daily = []
    for day, rec in sorted(by_day.items()):
        count = rec["count"]
        if count > 0:
            rec["avg_multiplier"] = rec["avg_multiplier"] / count
        rec["delta_pnl"] = rec["rl_pnl"] - rec["baseline_pnl"]
        rec["changed_pct"] = (rec["changed_count"] / count) if count else 0.0
        rec["day"] = day
        daily.append(rec)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "min_days_shadow": getattr(cfg, "RL_MIN_DAYS_SHADOW", 7),
        "promotion_rules": getattr(cfg, "RL_PROMOTION_RULES", "brier_improve_and_tail_ok"),
        "days": daily,
    }


def write_report(report: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with tmp.open("w") as f:
        json.dump(report, f, indent=2)
    tmp.replace(path)


def main():
    events = load_decision_events(DECISION_JSONL)
    report = build_report(events)
    write_report(report, REPORT_PATH)
    print(f"RL shadow report written: {REPORT_PATH}")


if __name__ == "__main__":
    main()
