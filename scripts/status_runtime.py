#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.paths import logs_dir, repo_root


PROCESS_SPECS = {
    "main": {"pidfile": "main.pid", "match": "main.py"},
    "scheduler": {"pidfile": "scheduler.pid", "match": "scheduler.py"},
    "streamlit": {"pidfile": "streamlit.pid", "match": "streamlit run"},
    "watchdog": {"pidfile": "watchdog.pid", "match": "watchdog.sh"},
}


def _read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


def _pid_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _ps_rows() -> list[tuple[int | None, str]]:
    try:
        result = subprocess.run(
            ["ps", "-ax", "-o", "pid=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    rows: list[tuple[int | None, str]] = []
    for raw in (result.stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        pid = None
        cmd = ""
        if parts:
            try:
                pid = int(parts[0])
            except Exception:
                pid = None
        if len(parts) > 1:
            cmd = parts[1]
        rows.append((pid, cmd))
    return rows


def _process_state(name: str, root: Path, ps_rows: list[tuple[int | None, str]]) -> dict:
    spec = PROCESS_SPECS[name]
    pidfile = root / "logs" / spec["pidfile"]
    pid = None
    pidfile_alive = False
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None
        pidfile_alive = _pid_alive(pid)
    if pidfile_alive:
        return {
            "name": name,
            "running": True,
            "pid": pid,
            "source": "pidfile",
            "pidfile": str(pidfile),
        }
    match = str(spec["match"])
    for row_pid, cmd in ps_rows:
        if match in str(cmd or ""):
            return {
                "name": name,
                "running": True,
                "pid": row_pid,
                "source": "ps",
                "pidfile": str(pidfile),
            }
    return {
        "name": name,
        "running": False,
        "pid": pid,
        "source": "pidfile" if pid is not None else "missing",
        "pidfile": str(pidfile),
    }


def build_status_report(*, root: Path | None = None, runtime_logs: Path | None = None) -> dict:
    repo = Path(root or repo_root())
    runtime_dir = Path(runtime_logs or logs_dir())
    suggestions = _read_json(runtime_dir / "suggestions_status.json")
    engine = _read_json(runtime_dir / "engine_cycle_status.json")
    feed = _read_json(runtime_dir / "feed_runtime_latest.json")
    ps_rows = _ps_rows()
    processes = {
        name: _process_state(name, repo, ps_rows)
        for name in PROCESS_SPECS
    }
    return {
        "repo_root": str(repo),
        "runtime_logs": str(runtime_dir),
        "process_logs": str(repo / "logs"),
        "market_mode": suggestions.get("market_mode", engine.get("market_mode")),
        "market_open": suggestions.get("market_open", engine.get("market_open")),
        "suggestions": suggestions,
        "engine": engine,
        "feed": feed,
        "processes": processes,
    }


def render_status_report(report: dict) -> str:
    suggestions = dict(report.get("suggestions") or {})
    engine = dict(report.get("engine") or {})
    feed = dict(report.get("feed") or {})
    processes = dict(report.get("processes") or {})
    lines = [
        f"Runtime logs: {report.get('runtime_logs')}",
        f"Process logs/pids: {report.get('process_logs')}",
        f"Market: mode={report.get('market_mode')} open={report.get('market_open')}",
        (
            "Suggestions: "
            f"status={suggestions.get('status')} count={suggestions.get('suggestion_count')} "
            f"primary_blocker={suggestions.get('primary_blocker')} "
            f"latest_trade_id={suggestions.get('latest_trade_id')} "
            f"latest_entry_status={suggestions.get('latest_entry_status')} "
            f"latest_permission={suggestions.get('latest_permission')}"
        ),
        (
            "Engine: "
            f"cycle_ok={engine.get('cycle_ok')} stage={engine.get('cycle_stage')} "
            f"mode={engine.get('market_mode')} open={engine.get('market_open')} "
            f"seen={engine.get('candidates_seen')} blocked={engine.get('candidates_blocked')} "
            f"enqueued={engine.get('candidates_enqueued')} primary_blocker={engine.get('primary_blocker')} "
            f"reason={engine.get('reason')} subreason={engine.get('subreason')}"
        ),
        (
            "Feed: "
            f"ws_connected={feed.get('ws_connected')} "
            f"subscribed_option_tokens_count={feed.get('subscribed_option_tokens_count')} "
            f"missing_option_tokens_count={feed.get('missing_option_tokens_count')}"
        ),
        "Processes:",
    ]
    for name in ("main", "scheduler", "streamlit", "watchdog"):
        proc = dict(processes.get(name) or {})
        lines.append(
            f"  - {name}: running={proc.get('running')} pid={proc.get('pid')} source={proc.get('source')} pidfile={proc.get('pidfile')}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show one-shot runtime status for tradebot.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON instead of text.")
    args = parser.parse_args()
    report = build_status_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_status_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
