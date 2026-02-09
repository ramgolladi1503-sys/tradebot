import argparse
import sqlite3
import sys
from pathlib import Path


REQUIRED_TABLES = {
    "decision_events",
    "ticks",
    "depth_snapshots",
}


def _check_db(path: Path):
    if not path.exists():
        print(f"ERROR:DR_DB_MISSING {path}", file=sys.stderr)
        return False
    try:
        conn = sqlite3.connect(path)
        cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cur.fetchall()}
        missing = REQUIRED_TABLES - tables
        if missing:
            print(f"ERROR:DR_DB_TABLES_MISSING {path} missing={sorted(missing)}", file=sys.stderr)
            return False
        conn.execute("SELECT COUNT(*) FROM decision_events")
        conn.close()
        return True
    except Exception as e:
        print(f"ERROR:DR_DB_VERIFY_FAILED {path} err={e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, help="Restored state directory")
    args = parser.parse_args()

    state = Path(args.state)
    db_paths = list(state.glob("**/*.db"))
    if not db_paths:
        print("ERROR:DR_NO_DB_FOUND", file=sys.stderr)
        raise SystemExit(2)

    ok = True
    for db in db_paths:
        if not _check_db(db):
            ok = False

    if not ok:
        raise SystemExit(2)
    print("DR verify OK")


if __name__ == "__main__":
    main()
