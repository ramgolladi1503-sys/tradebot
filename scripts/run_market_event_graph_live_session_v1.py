#!/usr/bin/env python3
"""Deterministic orchestrator for a Kite live-observation session."""

from __future__ import annotations

import argparse
import hashlib
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
from core.market_event_graph_live_observation_registry import build_observation_subscription_merge
from config import config as cfg
from core.session_calendar import is_open


def _validate_session_date(session_date: str) -> str:
    parsed = datetime.strptime(session_date, "%Y-%m-%d")
    if parsed.weekday() >= 5:
        raise SystemExit("BLOCKED_BY_NSE_SESSION_CALENDAR")
    return parsed.date().isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    if not args.preflight_only:
        master_path = _kite_master_json_for_run(args)
    else:
        if args.kite_instruments_file is None:
            raise SystemExit("BLOCKED_BY_KITE_MASTER_FILE_REQUIRED")
        master_path = args.kite_instruments_file
    if not master_path.is_absolute():
        master_path = (REPO_ROOT / master_path).resolve()
    if not master_path.is_file():
        raise SystemExit("BLOCKED_BY_KITE_MASTER_FILE_MISSING")
    master_sha = _sha256(master_path)
    expected_master_sha = "828c0c378e4939720c34ee7e727e5ae6f0265441e0e0a1888a386f85ab9c2a93"
    if master_sha != expected_master_sha:
        raise SystemExit("BLOCKED_BY_KITE_MASTER_HASH")
    linked_sha = str((registry.contract.get("broker_instrument_master") or {}).get("sha256") or "")
    if linked_sha != master_sha:
        raise SystemExit("BLOCKED_BY_CONTRACT_MASTER_MISMATCH")
    # Preflight is deliberately offline.  The deterministic production portion
    # is the configured underlying/index token set; option-window expansion is
    # broker-dependent and therefore cannot be claimed by this command.
    configured_indices = getattr(cfg, "INDEX_TOKEN_BY_SYMBOL", {}) or {}
    production_tokens = [int(configured_indices[symbol]) for symbol in getattr(cfg, "SYMBOLS", []) if symbol in configured_indices]
    resolution = [{"symbol": symbol, "index_token": int(configured_indices[symbol]), "source": "config"} for symbol in getattr(cfg, "SYMBOLS", []) if symbol in configured_indices]
    budget = int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150))
    decision = build_observation_subscription_merge(
        production_tokens=list(production_tokens or []),
        observation_tokens=list(registry.all_tokens),
        budget=budget,
    )
    preflight = dict(decision)
    preflight.update({
        "ok": bool(decision["ok"]),
        "reason": decision["reason"],
        "session_date": session_date,
        "contract_path": registry.contract_path,
        "contract_sha256": _sha256(Path(registry.contract_path)),
        "canonical_universe_sha256": registry.canonical_sha256,
        "kite_instruments_file": str(master_path),
        "kite_instruments_sha256": master_sha,
        "constituent_count": len(registry.constituent_symbols),
        "observed_token_count": registry.token_count,
        "production_token_count": len(production_tokens or []),
        "production_resolution_count": len(resolution or []),
        "capture_session_id": f"meg-live-{session_date}-{hashlib.sha256((str(args.output_root.resolve()) + session_date).encode()).hexdigest()[:16]}",
        "read_only": True, "is_order_action": False, "broker_api_called": False,
        "allowed_for_live_execution": False,
    })
    preflight["session_date"] = session_date
    preflight["contract_path"] = registry.contract_path
    preflight["observed_token_count"] = registry.token_count
    if args.preflight_only:
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
