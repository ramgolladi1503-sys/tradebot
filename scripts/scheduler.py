#!/usr/bin/env python3
"""
IST-based premarket scheduler (timezone-safe, idempotent).

Runs premarket reports at 09:00 IST daily (with grace window).
If system was asleep, runs immediately on wake and logs delay.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.time_utils import now_ist, ist_date_key, within_window


LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
STATE_PATH = Path(os.getenv("SCHEDULER_STATE_PATH", str(LOG_DIR / "scheduler_state.json")))
SCHED_LOG = LOG_DIR / "scheduler.log"

TARGET_TIME = os.getenv("PREMARKET_TARGET_HHMM", "09:00")
GRACE_MINUTES = int(os.getenv("PREMARKET_GRACE_MIN", "10"))
CHECK_INTERVAL_SEC = int(os.getenv("PREMARKET_CHECK_INTERVAL_SEC", "30"))

# Premarket scripts list (order matters)
PREMARKET_SCRIPTS = [
    "scripts/premarket_plan.py",
]


@dataclass
class Decision:
    should_run: bool
    reason: str
    delay_min: float
    already_ran: bool


def _log_event(kind: str, payload: Dict[str, object]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    base = {
        "event": kind,
        "ts_epoch": time.time(),
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "ts_local": datetime.now().astimezone().isoformat(),
        "ts_ist": now_ist().isoformat(),
    }
    base.update(payload)
    with SCHED_LOG.open("a") as f:
        f.write(json.dumps(base) + "\n")


def _load_state(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_state(path: Path, state: Dict[str, object]) -> None:
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _resolve_python() -> str:
    return os.getenv("PYTHON_BIN") or sys.executable or "python"


def _target_dt(now: datetime) -> datetime:
    try:
        hh, mm = [int(x) for x in TARGET_TIME.split(":", 1)]
    except Exception:
        hh, mm = 9, 0
    return now.replace(hour=hh, minute=mm, second=0, microsecond=0)


def should_run_premarket(now: Optional[datetime], last_run_date: Optional[str]) -> Decision:
    now = now or now_ist()
    date_key = ist_date_key(now)
    if last_run_date == date_key:
        return Decision(False, "already_ran_today", 0.0, True)
    target_dt = _target_dt(now)
    if now < target_dt:
        return Decision(False, "too_early", 0.0, False)
    if within_window(now, target_hhmm=TARGET_TIME, grace_minutes=GRACE_MINUTES):
        delay_min = max(0.0, (now - target_dt).total_seconds() / 60.0)
        return Decision(True, "on_time", delay_min, False)
    delay_min = max(0.0, (now - target_dt).total_seconds() / 60.0)
    return Decision(True, "delayed", delay_min, False)


def _run_scripts(date_key: str) -> None:
    py = _resolve_python()
    run_log = LOG_DIR / f"premarket_run_{date_key}.log"
    LOG_DIR.mkdir(exist_ok=True)
    start = time.time()
    _log_event("PREMARKET_RUN_START", {"date_key": date_key, "scripts": PREMARKET_SCRIPTS})
    with run_log.open("a") as f:
        for script in PREMARKET_SCRIPTS:
            script_path = Path(script)
            if not script_path.exists():
                msg = f"missing_script:{script}"
                _log_event("PREMARKET_SCRIPT_MISSING", {"date_key": date_key, "script": script})
                raise RuntimeError(msg)
            f.write(f"\n=== Running {script} ===\n")
            proc = subprocess.run([py, str(script_path)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            output = proc.stdout or ""
            if output:
                f.write(output)
                for line in output.splitlines():
                    _log_event("SCRIPT_OUTPUT", {"date_key": date_key, "script": script, "line": line[:2000]})
            if proc.returncode != 0:
                _log_event(
                    "PREMARKET_SCRIPT_FAIL",
                    {"date_key": date_key, "script": script, "code": proc.returncode},
                )
                raise RuntimeError(f"script_failed:{script}:code={proc.returncode}")
    duration = time.time() - start
    _log_event("PREMARKET_RUN_OK", {"date_key": date_key, "duration_sec": round(duration, 2)})


def _write_failure_marker(date_key: str, reason: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    marker = LOG_DIR / f"premarket_failed_{date_key}.txt"
    marker.write_text(f"{reason}\n")


def _print_check(decision: Decision, date_key: str) -> None:
    local_ts = datetime.now().astimezone().isoformat()
    ist_ts = now_ist().isoformat()
    print(f"local_time={local_ts}")
    print(f"ist_time={ist_ts}")
    if decision.should_run:
        print(f"WOULD_RUN reason={decision.reason} delay_min={decision.delay_min:.1f} date_key={date_key}")
    else:
        print(f"SKIP reason={decision.reason} date_key={date_key}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-now", action="store_true", help="Check whether scheduler would run now.")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    _log_event("SCHEDULER_START", {"target": TARGET_TIME, "grace_min": GRACE_MINUTES})

    state = _load_state(STATE_PATH)
    last_run = str(state.get("last_run_ist_date") or "")
    date_key = ist_date_key()
    decision = should_run_premarket(now_ist(), last_run if last_run else None)

    if args.check_now:
        _print_check(decision, date_key)
        return 0

    while True:
        state = _load_state(STATE_PATH)
        last_run = str(state.get("last_run_ist_date") or "")
        date_key = ist_date_key()
        decision = should_run_premarket(now_ist(), last_run if last_run else None)

        if not decision.should_run:
            _log_event("SCHEDULER_SKIP", {"reason": decision.reason, "date_key": date_key})
            time.sleep(CHECK_INTERVAL_SEC)
            continue

        _log_event(
            "SCHEDULER_TRIGGER",
            {"reason": decision.reason, "delay_min": round(decision.delay_min, 2), "date_key": date_key},
        )
        try:
            _run_scripts(date_key)
        except Exception as exc:
            _write_failure_marker(date_key, str(exc))
            _log_event("PREMARKET_RUN_FAIL", {"date_key": date_key, "error": str(exc)})
            return 1

        # Update state only on success
        state["last_run_ist_date"] = date_key
        state["last_run_ts_epoch"] = time.time()
        _save_state(STATE_PATH, state)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
