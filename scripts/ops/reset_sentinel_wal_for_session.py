#!/usr/bin/env python3
"""Beginning of Day (BOD) Operational Script: Reset Sentinel APM WAL States.

Causally purges stale overnight or crash recovery states (COOL_OFF, CRASH_RECOVERY)
across NIFTY, SENSEX, and BANKNIFTY WAL files, resetting them to STATE_STANDBY
for a pristine trading session startup.
"""

import argparse
import json
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

TARGET_WAL_FILES = [
    "runtime/sentinel_apm_wal.json",
    "runtime/sentinel_apm_wal_sensex.json",
    "runtime/sentinel_apm_wal_banknifty.json",
]


def reset_wal_file(filepath: Path, today_str: str, dry_run: bool = False) -> bool:
    if not filepath.exists():
        print(f"[*] WAL file {filepath} does not exist. Creating clean STANDBY state.")
        if dry_run:
            return True
        filepath.parent.mkdir(parents=True, exist_ok=True)
        init_payload = {
            "state": "STANDBY",
            "last_completed_trade": None,
            "cool_off_until": None,
            "cool_off_ref_spot": None,
            "cool_off_direction": None,
            "session_date": today_str,
            "reset_reason": "BOD_INITIALIZATION",
            "persisted_at": datetime.now().isoformat(),
        }
        with open(filepath, "w") as f:
            json.dump(init_payload, f, indent=2)
        return True

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] Warning: corrupt WAL file {filepath} ({e}). Re-initializing clean STANDBY.")
        data = {}

    curr_state = data.get("state", "UNKNOWN")
    cool_off_until = data.get("cool_off_until")
    last_trade = data.get("last_completed_trade") or {}
    entry_time = last_trade.get("entry_time", "")

    is_stale_date = False
    if entry_time and entry_time[:10] != today_str:
        is_stale_date = True

    needs_reset = (curr_state != "STANDBY") or is_stale_date or (cool_off_until is not None)

    if not needs_reset:
        print(f"[✓] {filepath.name} is already clean in STANDBY for {today_str}.")
        return False

    print(f"[→] Resetting {filepath.name} (Current state: {curr_state}, Stale date: {is_stale_date}, Cool-off: {cool_off_until})")

    if dry_run:
        print(f"    [DRY-RUN] Would archive and reset {filepath.name} to STANDBY.")
        return True

    # 1. Archive previous WAL
    archive_dir = filepath.parent.parent / "logs" / "wal_archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_file = archive_dir / f"{filepath.stem}_{timestamp_str}.json"
    shutil.copy2(filepath, archive_file)
    print(f"    [✓] Archived stale WAL to {archive_file}")

    # 2. Prepare clean STANDBY state while preserving completed trade record for audit
    clean_data = {
        "state": "STANDBY",
        "last_completed_trade": last_trade if not is_stale_date else None,
        "cool_off_until": None,
        "cool_off_ref_spot": None,
        "cool_off_direction": None,
        "session_date": today_str,
        "reset_reason": "BOD_PREFLIGHT_CLEAN_SLATE",
        "persisted_at": datetime.now().isoformat(),
    }

    # Atomic write via temporary file
    tmp_path = filepath.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(clean_data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())

    os.replace(tmp_path, filepath)
    print(f"    [✓] Atomically wrote clean STANDBY state to {filepath.name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Reset Sentinel APM WAL States for BOD Preflight")
    parser.add_argument("--dry-run", action="store_true", help="Report without modifying files")
    parser.add_argument("--force", action="store_true", help="Execute without interactive confirmation")
    parser.add_argument("--session-date", type=str, default="", help="Explicit YYYY-MM-DD date")
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent.parent.parent
    os.chdir(repo_dir)

    today_str = args.session_date or datetime.now().strftime("%Y-%m-%d")
    print(f"==================================================================")
    print(f"[*] Sentinel BOD WAL Reset Preflight Utility (Session: {today_str})")
    print(f"==================================================================")

    reset_count = 0
    for wal_rel in TARGET_WAL_FILES:
        wal_path = repo_dir / wal_rel
        if reset_wal_file(wal_path, today_str, dry_run=args.dry_run):
            reset_count += 1

    print(f"[*] BOD WAL Reset complete. {reset_count} file(s) updated.")
    sys.exit(0)


if __name__ == "__main__":
    main()
