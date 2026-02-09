import argparse
import json
import sqlite3
from pathlib import Path

from config import config as cfg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    args = parser.parse_args()

    db_path = Path(getattr(cfg, "DECISION_SQLITE_PATH", "logs/decision_events.sqlite"))
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM experiments WHERE experiment_id=?", (args.id,))
        row = cur.fetchone()
        if not row:
            raise SystemExit("Experiment not found")
        if row[0] not in ("STOPPED",):
            raise SystemExit("Experiment must be STOPPED to analyze")
    report = {"experiment_id": args.id, "status": "ANALYZED", "note": "analysis_placeholder"}
    out = Path("logs") / f"experiment_{args.id}_analysis.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(f"Experiment analysis: {out}")


if __name__ == "__main__":
    main()
