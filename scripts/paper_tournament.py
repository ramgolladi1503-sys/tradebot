import argparse
import json
import random
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg


def _utc_iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _load_outcomes(db_path: Path, start_epoch: float) -> list[dict]:
    if not db_path.exists():
        return []
    rows = []
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT trade_id, r_multiple, timestamp_epoch FROM outcomes WHERE timestamp_epoch IS NOT NULL AND timestamp_epoch >= ?",
            (start_epoch,),
        )
        for trade_id, r_multiple, ts in cur.fetchall():
            if r_multiple is None or ts is None:
                continue
            rows.append({"trade_id": trade_id, "r_multiple": float(r_multiple), "timestamp_epoch": float(ts)})
    return rows


def _load_trades(db_path: Path, trade_ids: set[str]) -> list[dict]:
    if not db_path.exists() or not trade_ids:
        return []
    rows = []
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        q = "SELECT trade_id, strategy FROM trades WHERE trade_id IN ({})".format(
            ",".join("?" for _ in trade_ids)
        )
        cur.execute(q, list(trade_ids))
        for trade_id, strategy in cur.fetchall():
            rows.append({"trade_id": trade_id, "strategy": strategy})
    return rows


def _compute_stats(r_vals: list[float]) -> dict:
    if not r_vals:
        return {"trades": 0, "expectancy": 0.0, "win_rate": 0.0, "drawdown": 0.0, "stability": 0.0}
    mean_r = sum(r_vals) / len(r_vals)
    win_rate = sum(1 for r in r_vals if r > 0) / len(r_vals)
    cum = 0.0
    peak = 0.0
    dd = 0.0
    for r in r_vals:
        cum += r
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    stability = mean_r / (abs(dd) + 1e-6)
    return {
        "trades": len(r_vals),
        "expectancy": mean_r,
        "win_rate": win_rate,
        "drawdown": dd,
        "stability": stability,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    now = time.time()
    start_epoch = now - args.days * 86400
    db_path = Path(getattr(cfg, "TRADE_DB_PATH", "data/trades.db"))

    outcomes = _load_outcomes(db_path, start_epoch)
    trade_ids = {o["trade_id"] for o in outcomes}
    trades = _load_trades(db_path, trade_ids)
    strat_by_id = {t["trade_id"]: t.get("strategy") for t in trades}

    strat_r: dict[str, list[float]] = {}
    for o in outcomes:
        strat = strat_by_id.get(o["trade_id"], "UNKNOWN")
        strat_r.setdefault(strat, []).append(o["r_multiple"])

    report = {
        "as_of_epoch": now,
        "as_of_iso": _utc_iso(now),
        "days": args.days,
        "seed": args.seed,
        "strategies": [],
        "notes": [],
    }

    if not strat_r:
        report["notes"].append("no_outcomes_in_range")
    else:
        for strat, r_vals in sorted(strat_r.items()):
            stats = _compute_stats(r_vals)
            status = "HOLD"
            if stats["trades"] < cfg.TOURNAMENT_MIN_TRADES:
                status = "INSUFFICIENT_DATA"
            elif stats["expectancy"] >= cfg.TOURNAMENT_PROMOTE_SCORE and stats["win_rate"] >= cfg.TOURNAMENT_MIN_WINRATE:
                status = "PROMOTE_CANDIDATE"
            elif stats["drawdown"] <= cfg.TOURNAMENT_QUARANTINE_DD:
                status = "QUARANTINE_CANDIDATE"
            report["strategies"].append({"strategy": strat, **stats, "status": status})

    out = Path("logs/tournament_report.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Tournament report: {out}")


if __name__ == "__main__":
    main()
