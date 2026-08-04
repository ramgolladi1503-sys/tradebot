#!/usr/bin/env python3
import sys
import sqlite3
import argparse
from pathlib import Path
import logging

sys.path.append(str(Path(__file__).parent.parent.parent))

from core.upstox_capture.replay_adapter import ReplayAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("replay_run")

def verify_database_counts(db_path: Path):
    if not db_path.exists():
        logger.error(f"Database {db_path} does not exist.")
        return

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT count(*) FROM ticks")
        ticks_count = cursor.fetchone()[0]

        cursor.execute("SELECT count(*) FROM depth_snapshots")
        depth_count = cursor.fetchone()[0]

        logger.info(f"Replay Database Verification Report:")
        logger.info(f"  ticks count: {ticks_count}")
        logger.info(f"  depth_snapshots count: {depth_count}")
        conn.close()
    except Exception as e:
        logger.error(f"Failed to verify database tables: {e}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, help="Path to the capture run root directory")
    parser.add_argument("--db-path", required=True, help="Path to the output replay SQLite database")
    parser.add_argument("--mode", default="MAX_SPEED", choices=["MAX_SPEED", "RAW_FAITHFUL", "ACCELERATED"], help="Replay timing mode")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    db_path = Path(args.db_path)

    logger.info(f"Starting offline replay adapter...")
    logger.info(f"  Run directory: {run_dir}")
    logger.info(f"  Replay mode: {args.mode}")

    # Remove stale replay DB if it exists
    if db_path.exists():
        logger.info(f"Removing old replay database: {db_path}")
        db_path.unlink()

    adapter = ReplayAdapter(run_dir, db_path, args.mode)
    try:
        adapter.run()
        verify_database_counts(db_path)
        logger.info("Replay completed successfully.")
    except Exception as e:
        logger.error(f"Replay run failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
