#!/usr/bin/env python3
"""Deterministic orchestrator for a Kite live-observation session."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import config as cfg
from core.market_event_graph_live_launch_plan import (
    PASS_STATIC_LIVE_SOURCE_PREFLIGHT,
    build_launch_plan,
    write_launch_plan,
)
from core.market_event_graph_live_observation_registry import load_observation_registry
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


def _resolve_master_path(args: argparse.Namespace) -> tuple[Path, bool]:
    if args.kite_instruments_file is not None:
        master_path = args.kite_instruments_file
        broker_metadata_called = False
    elif args.preflight_only or args.static_preflight_only:
        raise SystemExit("BLOCKED_BY_KITE_MASTER_FILE_REQUIRED")
    else:
        master_path = _kite_master_json_for_run(args)
        broker_metadata_called = True
    if not master_path.is_absolute():
        master_path = (REPO_ROOT / master_path).resolve()
    return master_path, broker_metadata_called


def _commit_sha() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _static_preflight_payload(*, session_date: str, registry: Any, master_path: Path, output_root: Path) -> dict[str, Any]:
    capture_dir = output_root / session_date
    governed_files = [
        capture_dir / "captured_metadata.jsonl",
        capture_dir / "launch_plan.json",
        capture_dir / "presession_manifest.json",
        capture_dir / "live_observation.log",
    ]
    output_unused = not capture_dir.exists() and not any(path.exists() for path in governed_files)
    return {
        "ok": bool(output_unused),
        "verdict": PASS_STATIC_LIVE_SOURCE_PREFLIGHT if output_unused else "BLOCKED_BY_GOVERNED_OUTPUT_COLLISION",
        "session_date": session_date,
        "session_day_open": bool(is_open(datetime.strptime(session_date, "%Y-%m-%d"))),
        "contract_path": registry.contract_path,
        "contract_sha256": _sha256(Path(registry.contract_path)),
        "canonical_universe_sha256": registry.canonical_sha256,
        "kite_instruments_file": str(master_path),
        "kite_instruments_sha256": _sha256(master_path),
        "constituent_count": len(registry.constituent_symbols),
        "observed_token_count": registry.token_count,
        "output_root": str(output_root),
        "capture_dir": str(capture_dir),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }


def _build_production_launch_plan(
    *,
    session_date: str,
    registry: Any,
    master_sha: str,
    broker_metadata_called: bool,
) -> dict[str, Any]:
    from core import kite_depth_ws

    budget = int(getattr(cfg, "DEPTH_SUBSCRIPTION_MAX_TOKENS", 150))
    try:
        production_tokens, resolution = kite_depth_ws.build_subscription_tokens(list(cfg.SYMBOLS), max_tokens=budget)
    except BaseException as exc:
        return {
            "ok": False,
            "verdict": "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN",
            "reason": f"{type(exc).__name__}:{exc}",
            "production_token_count": 0,
            "configured_budget": budget,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_metadata_called": bool(broker_metadata_called),
            "allowed_for_live_execution": False,
        }
    if not production_tokens:
        return {
            "ok": False,
            "verdict": "BLOCKED_BY_PRODUCTION_SUBSCRIPTION_PLAN_UNPROVEN",
            "production_token_count": 0,
            "configured_budget": budget,
            "read_only": True,
            "is_order_action": False,
            "broker_api_called": False,
            "broker_metadata_called": bool(broker_metadata_called),
            "allowed_for_live_execution": False,
        }
    sticky_tokens = []
    try:
        sticky_tokens = list(kite_depth_ws.get_sticky_tokens())
    except Exception:
        sticky_tokens = []
    return build_launch_plan(
        session_date=session_date,
        production_tokens=production_tokens,
        production_resolution=resolution,
        sticky_tokens=sticky_tokens,
        observation_tokens=list(registry.all_tokens),
        budget=budget,
        master_sha256=master_sha,
        universe_sha256=registry.canonical_sha256,
        configuration={
            "symbols": list(getattr(cfg, "SYMBOLS", []) or []),
            "depth_subscription_max_tokens": budget,
            "depth_subscription_strikes_around": getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND", None),
            "depth_subscription_strikes_around_by_symbol": getattr(cfg, "DEPTH_SUBSCRIPTION_STRIKES_AROUND_BY_SYMBOL", None),
            "min_option_tokens": getattr(cfg, "MIN_OPTION_TOKENS", None),
        },
        broker_metadata_called=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--kite-instruments-file", type=Path, default=None)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--static-preflight-only", action="store_true")
    parser.add_argument("--launch-preflight-only", action="store_true")
    args = parser.parse_args()

    session_date = _validate_session_date(args.session_date)
    args.output_root.mkdir(parents=True, exist_ok=True)
    registry = load_observation_registry(force=True)
    if registry is None:
        raise SystemExit(2)
    master_path, broker_metadata_called = _resolve_master_path(args)
    if not master_path.is_file():
        raise SystemExit("BLOCKED_BY_KITE_MASTER_FILE_MISSING")
    master_sha = _sha256(master_path)
    expected_master_sha = "828c0c378e4939720c34ee7e727e5ae6f0265441e0e0a1888a386f85ab9c2a93"
    if master_sha != expected_master_sha:
        raise SystemExit("BLOCKED_BY_KITE_MASTER_HASH")
    linked_sha = str((registry.contract.get("broker_instrument_master") or {}).get("sha256") or "")
    if linked_sha != master_sha:
        raise SystemExit("BLOCKED_BY_CONTRACT_MASTER_MISMATCH")
    static_preflight = _static_preflight_payload(
        session_date=session_date,
        registry=registry,
        master_path=master_path,
        output_root=args.output_root.resolve(),
    )
    if args.preflight_only or args.static_preflight_only:
        print(json.dumps(static_preflight, sort_keys=True))
        return 0 if bool(static_preflight.get("ok")) else 2

    launch_plan = _build_production_launch_plan(
        session_date=session_date,
        registry=registry,
        master_sha=master_sha,
        broker_metadata_called=broker_metadata_called,
    )
    if args.launch_preflight_only:
        print(json.dumps(launch_plan, sort_keys=True))
        return 0 if bool(launch_plan.get("ok")) else 2

    if not bool(static_preflight.get("ok")) or not bool(launch_plan.get("ok")):
        print(json.dumps({"static_preflight": static_preflight, "launch_preflight": launch_plan}, sort_keys=True))
        return 2

    plan_sha = str(launch_plan["launch_plan_sha256"])
    run_nonce = hashlib.sha256(f"{session_date}:{plan_sha}:{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
    run_id = f"meg-live-{session_date}-{plan_sha[:12]}-{run_nonce}"
    capture_dir = args.output_root.resolve() / session_date / run_id
    capture_dir.mkdir(parents=True, exist_ok=False)
    launch_plan_path = capture_dir / "launch_plan.json"
    write_launch_plan(launch_plan_path, launch_plan)
    manifest = {
        "launch_plan_sha256": plan_sha,
        "master_sha256": master_sha,
        "universe_sha256": registry.canonical_sha256,
        "commit_sha": _commit_sha(),
        "session_date": session_date,
        "capture_session_id": run_id,
        "output_paths": {
            "capture_dir": str(capture_dir),
            "captured_metadata": str(capture_dir / "captured_metadata.jsonl"),
            "launch_plan": str(launch_plan_path),
            "log": str(capture_dir / "live_observation.log"),
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "broker_metadata_called": bool(broker_metadata_called),
        "allowed_for_live_execution": False,
    }
    (capture_dir / "presession_manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    log_path = capture_dir / "live_observation.log"
    env = dict(os.environ)
    env.update(
        {
            "RUN_ID": run_id,
            "MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE": "true",
            "MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH": registry.contract_path,
            "MARKET_EVENT_GRAPH_LIVE_SOURCE_PATH": str(capture_dir / "captured_metadata.jsonl"),
            "MARKET_EVENT_GRAPH_LIVE_LAUNCH_PLAN_PATH": str(launch_plan_path),
        }
    )
    with log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.run(["bash", "run_live.sh"], cwd=REPO_ROOT, env=env, stdout=log_file, stderr=subprocess.STDOUT)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
