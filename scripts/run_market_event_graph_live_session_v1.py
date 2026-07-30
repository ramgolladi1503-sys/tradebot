#!/usr/bin/env python3
"""Deterministic orchestrator for a Kite live-observation session."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.market_event_graph_live_observation_registry import load_observation_registry, observation_budget_preflight


def _validate_session_date(session_date: str) -> str:
    parsed = datetime.strptime(session_date, "%Y-%m-%d")
    return parsed.date().isoformat()


def _kite_master_json_for_run(args: argparse.Namespace) -> Path:
    if args.kite_instruments_file is not None:
        return args.kite_instruments_file
    acquire_script = REPO_ROOT / "scripts" / "acquire_kite_instrument_master_v1.py"
    proc = subprocess.run(
        [
            sys.executable,
            "-B",
            str(acquire_script),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        raise SystemExit(f"failed to parse Kite master acquisition output: {exc}") from exc
    raw_path = payload.get("raw_path")
    if not raw_path:
        raise SystemExit(2)
    return Path(str(raw_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--kite-instruments-file", type=Path, default=None)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    session_date = _validate_session_date(args.session_date)
    args.output_root.mkdir(parents=True, exist_ok=True)
    registry = load_observation_registry(force=True)
    if registry is None:
        raise SystemExit(2)
    preflight = observation_budget_preflight(
        budget=None,
        current_tokens=[],
    )
    preflight["session_date"] = session_date
    preflight["contract_path"] = registry.contract_path
    preflight["observed_token_count"] = registry.token_count
    if args.preflight_only:
        preflight["kite_instruments_file"] = str(args.kite_instruments_file) if args.kite_instruments_file is not None else None
        print(json.dumps(preflight, sort_keys=True))
        return 0 if bool(preflight.get("ok", True)) else 2

    master_path = _kite_master_json_for_run(args)
    preflight["kite_instruments_file"] = str(master_path)
    run_id = f"meg-live-{session_date}"
    log_path = args.output_root / "live_observation" / f"{run_id}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(
        {
            "RUN_ID": run_id,
            "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE": "true",
            "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH": registry.contract_path,
            "MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH": str(args.output_root / "captured_metadata.jsonl"),
        }
    )
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.run(["bash", "run_live.sh"], cwd=REPO_ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
