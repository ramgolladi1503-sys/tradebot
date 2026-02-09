from datetime import datetime, timezone
from core.trade_store import insert_execution_stat, fetch_execution_stats


def main():
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    row = {
        "timestamp": ts,
        "instrument": "TEST",
        "slippage_bps": 1.23,
        "latency_ms": 45.6,
        "fill_ratio": 0.78,
    }
    insert_execution_stat(row)
    cols, rows = fetch_execution_stats(limit=1)
    if not rows:
        raise SystemExit("verify_execution_stat: no rows fetched")
    latest = dict(zip(cols, rows[0]))
    assert latest.get("instrument") == "TEST", "instrument mismatch"
    print("verify_execution_stat: OK")


if __name__ == "__main__":
    main()
