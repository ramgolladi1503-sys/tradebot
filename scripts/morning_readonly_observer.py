#!/usr/bin/env python3
"""Launch the existing governed read-only observation runtime only."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from core.kite_read_only_observation_runtime import run_observation, safe_environment, safety_contract


def load_manifest(session_root: Path) -> dict[str, object]:
    path = session_root / "preflight" / "session_root_manifest.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("root") != str(session_root.resolve()):
        raise RuntimeError("SESSION_ROOT_MANIFEST_MISMATCH")
    if payload.get("repository_local_live_writers") != 0:
        raise RuntimeError("REPOSITORY_LOCAL_LIVE_WRITER")
    if any(payload.get(key) is not False for key in ("broker_write_authority", "order_authority", "paper_authorized", "live_authorized")):
        raise RuntimeError("READ_ONLY_AUTHORITY_MANIFEST_FAILED")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--launch-plan", type=Path, required=True)
    parser.add_argument("--session-root", type=Path, required=True)
    parser.add_argument("--token-path", type=Path, required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--max-runtime-sec", type=float)
    args = parser.parse_args()
    root = args.session_root.resolve()
    manifest = load_manifest(root)
    plan = json.loads(args.launch_plan.read_text(encoding="utf-8"))
    if not plan.get("ok"):
        raise SystemExit("READ_ONLY_LAUNCH_PLAN_NOT_VERIFIED")
    if str(plan.get("session_date")) != args.session_date:
        raise SystemExit("READ_ONLY_LAUNCH_PLAN_DATE_MISMATCH")
    env = safe_environment()
    os.environ.update(env)
    contract = safety_contract(env, child_command=["core.kite_read_only_observation_runtime.py"])
    (root / "preflight" / "observer_safety_contract.json").write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    plan = dict(plan)
    plan["run_id"] = manifest["session_id"]
    plan["commit_sha"] = manifest["release_sha"]
    return run_observation(launch_plan=plan, output_root=root / "runtime", token_path=args.token_path, session_date=args.session_date, max_runtime_sec=args.max_runtime_sec)


if __name__ == "__main__":
    raise SystemExit(main())
