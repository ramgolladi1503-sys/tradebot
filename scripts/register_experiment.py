import argparse
import sqlite3
import time
from pathlib import Path

from config import config as cfg


def _init_db(db_path: Path):
    db_path.parent.mkdir(exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS experiments (
                experiment_id TEXT PRIMARY KEY,
                name TEXT,
                status TEXT,
                created_epoch REAL,
                started_epoch REAL,
                stopped_epoch REAL,
                metadata_json TEXT
            )
            """
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--metadata", default="{}")
    args = parser.parse_args()

    db_path = Path(getattr(cfg, "DECISION_SQLITE_PATH", "logs/decision_events.sqlite"))
    _init_db(db_path)
    now = time.time()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO experiments (experiment_id, name, status, created_epoch, metadata_json) VALUES (?,?,?,?,?)",
            (args.id, args.name, "REGISTERED", now, args.metadata),
        )
    print(f"Experiment registered: {args.id}")


if __name__ == "__main__":
    main()
