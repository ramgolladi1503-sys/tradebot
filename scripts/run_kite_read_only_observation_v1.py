#!/usr/bin/env python3
"""Governed entrypoint for real Kite data with zero execution authority."""

from __future__ import annotations

import argparse
import json
import os
import hashlib
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
from core.market_event_graph_live_launch_plan import load_launch_plan, verify_frozen_launch_plan

EXPECTED_MASTER_SHA256 = "828c0c378e4939720c34ee7e727e5ae6f0265441e0e0a1888a386f85ab9c2a93"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--kite-instruments-file", required=True, type=Path)
    parser.add_argument("--launch-plan", required=True, type=Path)
    parser.add_argument("--frozen-launch-plan", type=Path, default=None)
    parser.add_argument("--expected-semantic-sha256", default=None)
    parser.add_argument("--expected-resolver-snapshot-sha256", default=None)
    parser.add_argument("--campaign-id", default=None)
    parser.add_argument("--token-path", required=True, type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if not args.token_path.is_file():
        raise SystemExit("KITE_ACCESS_TOKEN_MISSING")
    digest = hashlib.sha256(args.kite_instruments_file.read_bytes()).hexdigest()
    if digest != EXPECTED_MASTER_SHA256:
        raise SystemExit("BLOCKED_BY_KITE_MASTER_HASH")
    os.environ["TRADING_BOT_TOKEN_PATH"] = str(args.token_path.resolve())
    plan_path = args.frozen_launch_plan or args.launch_plan
    if args.frozen_launch_plan is not None:
        if not args.expected_semantic_sha256 or not args.expected_resolver_snapshot_sha256:
            raise SystemExit("BLOCKED_BY_FROZEN_LAUNCH_PLAN:EXPECTED_HASH_MISSING")
        verify_frozen_launch_plan(
            plan_path,
            expected_semantic_sha256=args.expected_semantic_sha256,
            expected_resolver_snapshot_sha256=args.expected_resolver_snapshot_sha256,
            session_date=args.session_date,
            campaign_id=args.campaign_id,
        )
    plan = load_launch_plan(plan_path)
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
    return run_observation(
        launch_plan=plan,
        output_root=args.output_root,
        token_path=args.token_path,
        session_date=args.session_date,
    )


if __name__ == "__main__":
    raise SystemExit(main())
