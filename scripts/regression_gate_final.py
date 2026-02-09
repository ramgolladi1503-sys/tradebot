#!/usr/bin/env python
import argparse
import subprocess
import sys
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg
from core.time_utils import is_market_open_ist, to_ist


def _tail(text: str, lines: int = 80) -> str:
    buf = text.splitlines()
    return "\n".join(buf[-lines:])


def _guess_next_action(cmd: list[str], output: str) -> str:
    # Try to extract a file from traceback
    for line in reversed(output.splitlines()):
        if line.strip().startswith("File"):
            return f"NEXT ACTION: inspect {line.strip()}"
    mapping = {
        "compileall": "NEXT ACTION: fix syntax error in reported file",
        "pytest": "NEXT ACTION: open failing test and target module",
        "regression_gate_12_14.py": "NEXT ACTION: run scripts/regression_gate_12_14.py directly",
        "verify_audit_chain.py": "NEXT ACTION: check logs/audit_log.jsonl for tampering",
        "verify_decision_chain.py": "NEXT ACTION: check logs/decision_events.jsonl for tampering",
        "verify_risk_units.py": "NEXT ACTION: inspect core/risk_engine.py and core/risk_state.py",
        "verify_desk_paths.py": "NEXT ACTION: inspect config DESK_* paths",
        "verify_feed_sla.py": "NEXT ACTION: run scripts/sla_check.py and validate feeds",
        "run_pilot_checklist.py": "NEXT ACTION: resolve checklist reasons",
        "run_stress_tests.py": "NEXT ACTION: ensure DecisionEvents include quote_ts_epoch",
        "replay_day.py": "NEXT ACTION: ensure ticks/depth data exists in trades DB",
        "import_sanity.py": "NEXT ACTION: fix import errors in reported module",
    }
    for key, action in mapping.items():
        if key in " ".join(cmd):
            return action
    return "NEXT ACTION: inspect failing command output"


def _run_cmd(cmd: list[str]) -> None:
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("FAIL COMMAND:", " ".join(cmd))
        print("STDOUT (tail):")
        print(_tail(res.stdout))
        print("STDERR (tail):")
        print(_tail(res.stderr))
        print(_guess_next_action(cmd, res.stdout + "\n" + res.stderr))
        raise SystemExit(res.returncode)
    if res.stdout:
        print(_tail(res.stdout, 5))


def _most_recent_trade_date(db_path: Path) -> str:
    if not db_path.exists():
        raise SystemExit(f"Missing DB: {db_path}")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    tables = ["ticks", "depth_snapshots", "decision_events", "trades"]
    max_ts = None
    for table in tables:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cur.fetchone():
            continue
        try:
            cur.execute(f"SELECT MAX(timestamp_epoch) FROM {table}")
            val = cur.fetchone()[0]
            if val and (max_ts is None or val > max_ts):
                max_ts = val
        except Exception:
            continue
    conn.close()
    if not max_ts:
        raise SystemExit("No timestamp_epoch data found in DB; run feeds or replay.")
    dt = datetime.fromtimestamp(max_ts, tz=timezone.utc)
    return to_ist(dt).date().isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--market-open", action="store_true")
    args = parser.parse_args()

    if args.quick and args.full:
        raise SystemExit("Choose either --quick or --full")
    full_mode = args.full or not args.quick
    market_open = args.market_open or is_market_open_ist()

    commands = [
        ["python", "-m", "compileall", "."],
    ]

    if args.quick:
        commands.append(["python", "-m", "pytest", "-q", "tests/test_decision_logger_schema.py", "tests/test_regime_wrappers.py"])
    else:
        commands.append(["python", "-m", "pytest", "-q"])

    if full_mode:
        commands.append(["python", "scripts/regression_gate_12_14.py"])

    commands += [
        ["python", "scripts/verify_audit_chain.py"],
        ["python", "scripts/verify_decision_chain.py"],
        ["python", "scripts/verify_risk_units.py"],
        ["python", "scripts/verify_desk_paths.py"],
        ["python", "scripts/verify_feed_sla.py"] + (["--market-open"] if market_open else []),
        ["python", "scripts/run_pilot_checklist.py", "--dry-run"],
    ]

    if full_mode:
        commands.append(["python", "scripts/run_stress_tests.py"])
        replay_date = _most_recent_trade_date(Path(cfg.TRADE_DB_PATH))
        commands.append(["python", "scripts/replay_day.py", "--date", replay_date, "--speed", "100"])

    commands.append(["python", "scripts/import_sanity.py"])

    for cmd in commands:
        _run_cmd(cmd)

    print("PASS: regression_gate_final")
    return 0


if __name__ == "__main__":
    sys.exit(main())
