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

from core.kite_read_only_observation_runtime import run_observation, safe_environment
from core.market_event_graph_live_launch_plan import load_launch_plan
from core.daily_instrument_authority import validate_authority



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--kite-instruments-file", required=True, type=Path)
    parser.add_argument("--launch-plan", required=True, type=Path)
    parser.add_argument("--token-path", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--authority-artifact", required=True, type=Path)
    parser.add_argument("--parquet-export", action="store_true")
    parser.add_argument("--parquet-export-interval-seconds", type=float, default=15.0)
    args = parser.parse_args()
    if not args.token_path.is_file():
        raise SystemExit("KITE_ACCESS_TOKEN_MISSING")
    authority = validate_authority(artifact_path=args.authority_artifact, master_path=args.kite_instruments_file, session_date=args.session_date, source_sha=os.environ.get("TRADEBOT_COMMIT_SHA", ""), required_tokens=[])
    if not authority["ok"]:
        raise SystemExit(authority["verdict"])
    os.environ["TRADING_BOT_TOKEN_PATH"] = str(args.token_path.resolve())
    plan = load_launch_plan(args.launch_plan)
    env = safe_environment()
    os.environ.update(env)
    from core.kite_read_only_observation_runtime import assert_import_boundary, safety_contract
    contract = safety_contract(env, child_command=["read-only-observation"], child_pid=None)
    args.output_root.mkdir(parents=True, exist_ok=True)
    (args.output_root / "startup_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.validate_only:
        from core.auth import get_kite_client
        from core import kite_depth_ws
        from core.runtime_snapshot_producer import produce_and_store_runtime_snapshots
        assert_import_boundary()
        get_kite_client(repo_root_path=Path.cwd()).profile()
        return 0
    exporter = None
    try:
        if args.parquet_export:
            db_path = args.output_root / "db" / "DEFAULT.sqlite"
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
