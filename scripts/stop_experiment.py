import argparse
import sqlite3
import time
from pathlib import Path

from config import config as cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    db_path = Path(getattr(cfg, "DECISION_SQLITE_PATH", "logs/decision_events.sqlite"))
    now = time.time()
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM experiments WHERE experiment_id=?", (args.id,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("Experiment not found")
        if row[0] != "RUNNING":
            raise SystemExit(f"Cannot stop experiment in state {row[0]}")
        conn.execute(
            "UPDATE experiments SET status=?, stopped_epoch=? WHERE experiment_id=?",
            ("STOPPED", now, args.id),
        )
    print(f"Experiment stopped: {args.id}")


if __name__ == "__main__":
    main()
