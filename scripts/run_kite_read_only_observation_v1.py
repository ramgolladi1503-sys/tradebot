#!/usr/bin/env python3
"""Governed entrypoint for real Kite data with zero execution authority."""

from __future__ import annotations

import argparse
import json
import os
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# The repository's automatic sitecustomize hooks may preload CI-only broker
# fixtures before this entrypoint executes. They are forbidden in the
# read-only child and are not part of its runtime dependency graph.
for _module_name in tuple(sys.modules):
    if _module_name == "core.broker" or _module_name.startswith("core.broker."):
        sys.modules.pop(_module_name, None)

from core.market_event_graph_live_launch_plan import load_launch_plan
from core.daily_instrument_authority import validate_authority



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--kite-instruments-file", required=True, type=Path)
    parser.add_argument("--launch-plan", required=True, type=Path)
    parser.add_argument("--token-path", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--authority-artifact", required=True, type=Path)
    parser.add_argument("--parquet-export", action="store_true")
    parser.add_argument("--parquet-export-interval-seconds", type=float, default=15.0)
    parser.add_argument("--disk-budget-contract", type=Path)
    args = parser.parse_args()

    # This branch is deliberately local-only: do not establish runtime storage,
    # inspect credentials, sanitize a runtime environment, or import observer/auth
    # modules. It validates only the frozen local launch and instrument artifacts.
    if args.validate_only:
        authority = validate_authority(
            artifact_path=args.authority_artifact,
            master_path=args.kite_instruments_file,
            session_date=args.session_date,
            source_sha=os.environ.get("TRADEBOT_COMMIT_SHA", ""),
            required_tokens=[],
        )
        if not authority["ok"]:
            raise SystemExit(authority["verdict"])
        plan = load_launch_plan(args.launch_plan)
        if plan.get("session_date") != args.session_date:
            raise SystemExit("BLOCKED_BY_LAUNCH_PLAN_SESSION_DATE")
        return 0

    if args.token_path is None:
        raise SystemExit("KITE_TOKEN_PATH_REQUIRED_FOR_OBSERVATION")
    if not args.token_path.is_file():
        raise SystemExit("KITE_ACCESS_TOKEN_MISSING")
    from core.runtime_storage_authority import StorageAuthorityError, establish, bind_environment
    try:
        storage = establish(volume=Path("/Volumes/TradeBotData"), runtime_root=args.output_root)
    except StorageAuthorityError as exc:
        raise SystemExit(str(exc))
    bind_environment(storage)
    authority = validate_authority(artifact_path=args.authority_artifact, master_path=args.kite_instruments_file, session_date=args.session_date, source_sha=os.environ.get("TRADEBOT_COMMIT_SHA", ""), required_tokens=[])
    if not authority["ok"]:
        raise SystemExit(authority["verdict"])
    if args.disk_budget_contract is not None:
        from core.low_disk_safety_gate import derive_budget, evaluate, write_decision
        contract = json.loads(args.disk_budget_contract.read_text(encoding="utf-8"))
        budget = derive_budget(
            baseline_bytes=int(contract["observed_bytes"]),
            observed_bytes_per_second=float(contract["observed_bytes_per_second"]),
            remaining_session_seconds=int(contract["remaining_session_seconds"]),
            peak_transient_bytes=int(contract["peak_transient_bytes"]),
            shutdown_reserve_bytes=int(contract["shutdown_reserve_bytes"]),
        )
        decision = evaluate(args.output_root, budget)
        write_decision(args.output_root / "disk_budget_decision.json", decision)
        if decision.verdict != "PASS":
            raise SystemExit(f"DISK_BUDGET_{decision.verdict}")
    os.environ["TRADING_BOT_TOKEN_PATH"] = str(args.token_path.resolve())
    plan = load_launch_plan(args.launch_plan)
    from core.kite_read_only_observation_runtime import run_observation, safe_environment
    env = safe_environment()
    os.environ.update(env)
    from core.kite_read_only_observation_runtime import safety_contract
    contract = safety_contract(env, child_command=["read-only-observation"], child_pid=None)
    (args.output_root / "startup_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    exporter = None
    try:
        if args.parquet_export:
            from core.paths import db_dir
            db_path = db_dir() / "DEFAULT.sqlite"
            parquet_dir = args.output_root / "parquet"
            exporter = subprocess.Popen([
                sys.executable, str(ROOT / "scripts" / "export_sqlite_snapshot_to_parquet.py"),
                "--production-db", str(db_path),
                "--output-dir", str(parquet_dir),
                "--interval-seconds", str(max(0.1, args.parquet_export_interval_seconds)),
                "--status-path", str(args.output_root / "parquet_export_status.json"),
            ])
        return run_observation(
            launch_plan=plan,
            output_root=args.output_root,
            token_path=args.token_path,
            session_date=args.session_date,
        )
    finally:
        if exporter is not None and exporter.poll() is None:
            exporter.terminate()
            try:
                exporter.wait(timeout=5)
            except subprocess.TimeoutExpired:
                exporter.kill()
                exporter.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
