import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
import runpy

runpy.run_path(Path(__file__).with_name("bootstrap.py"))

from config import config as cfg
from core.freshness_sla import get_freshness_status


def _read_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def _tail_jsonl(path: Path, n: int = 5):
    if not path.exists():
        return []
    rows = []
    try:
        with path.open() as f:
            for line in f:
                if line.strip():
                    rows.append(line.strip())
        return [json.loads(r) for r in rows[-n:]]
    except Exception:
        return []


def _count_last_min(conn, table, now_epoch):
    try:
        cutoff = float(now_epoch) - 60.0
        row = conn.execute(
            f"""
            SELECT COUNT(*) FROM {table}
            WHERE (
                CASE
                    WHEN timestamp_epoch > 1e15 THEN timestamp_epoch / 1000000.0
                    WHEN timestamp_epoch > 1e12 THEN timestamp_epoch / 1000.0
                    ELSE timestamp_epoch
                END
            ) >= ?
            """,
            (cutoff,),
        ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def main():
    db = Path(cfg.TRADE_DB_PATH)
    if not db.exists():
        raise SystemExit("trades.db not found")
    conn = sqlite3.connect(db)
    now_epoch = time.time()
    tick_msgs = _count_last_min(conn, "ticks", now_epoch)
    depth_msgs = _count_last_min(conn, "depth_snapshots", now_epoch)
    conn.close()

    freshness = get_freshness_status(force=True)
    tick_lag = (freshness.get("ltp") or {}).get("age_sec")
    depth_lag = (freshness.get("depth") or {}).get("age_sec")

    print("Ops Summary")
    print("Feed Health")
    print(f"  tick_lag_sec: {tick_lag}")
    print(f"  depth_lag_sec: {depth_lag}")
    print(f"  tick_msgs_last_min: {tick_msgs}")
    print(f"  depth_msgs_last_min: {depth_msgs}")

    halt = _read_json(Path(cfg.RISK_HALT_FILE)) or {}
    print("Risk Halt")
    print(f"  halted: {halt.get('halted')}")
    print(f"  reason: {halt.get('reason')}")

    decay = _read_json(Path("logs/decay_report_" + datetime.now().strftime("%Y-%m-%d") + ".json"))
    if decay:
        print("Decay")
        print(f"  decaying: {len(decay.get('decaying', []))}")
        print(f"  quarantined: {len(decay.get('quarantined', []))}")

    strat_perf = _read_json(Path("logs/strategy_perf.json"))
    if strat_perf and isinstance(strat_perf, dict):
        stats = strat_perf.get("stats", {})
        top = sorted(stats.items(), key=lambda x: x[1].get("trades", 0), reverse=True)[:5]
        print("Strategy Perf (top trades)")
        for name, s in top:
            print(f"  {name}: trades={s.get('trades')} win_rate={s.get('win_rate')}")

    decisions = _tail_jsonl(Path(getattr(cfg, "DECISION_LOG_PATH", "logs/decision_events.jsonl")), n=5)
    if decisions:
        print("Recent Decisions")
        for d in decisions:
            print(f"  {d.get('ts')} {d.get('symbol')} gate={d.get('gatekeeper_allowed')} veto={d.get('veto_reasons')}")

    fillq = _read_json(Path("logs/execution_analytics.json"))
    if fillq:
        print("Execution Quality")
        print(f"  fill_ratio: {fillq.get('fill_ratio')}")
        print(f"  avg_latency_ms: {fillq.get('avg_latency_ms')}")
        print(f"  avg_slippage: {fillq.get('avg_slippage')}")


if __name__ == "__main__":
    main()
