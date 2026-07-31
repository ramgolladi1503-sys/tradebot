#!/usr/bin/env python3
"""Governed launcher for the PR #748-#756 unified evidence campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.unified_live_validation_pr748_756.campaign_contract import (
    ENABLE_ENV,
    build_campaign_identity,
    build_composition_manifest,
    current_commit_sha,
    reject_presession_live_run_id,
    require_campaign_enabled,
)
from core.unified_live_validation_pr748_756.launcher import launch_runtime_child


def _runtime_wired() -> bool:
    # This is deliberately conservative. It must become true only when main.py or
    # run_live.sh imports/initializes campaign observers, not when this helper exists.
    targets = (Path("main.py"), Path("run_live.sh"))
    needles = ("unified_live_validation_pr748_756", "UNIFIED_LIVE_VALIDATION_PR748_756")
    for path in targets:
        text = path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""
        if any(needle in text for needle in needles):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="runtime/diagnostics/unified_live_validation_pr748_756_v1")
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--nonce")
    parser.add_argument("--launch-live", action="store_true")
    parser.add_argument("--runtime-command", nargs=argparse.REMAINDER)
    parser.add_argument("--timeout-sec", type=float)
    args = parser.parse_args()

    require_campaign_enabled()
    root = Path(args.evidence_root)
    commit = current_commit_sha(".")
    manifest = build_composition_manifest(origin_main_sha=args.origin_main_sha, integrated_commit_sha=commit)
    presession = root / "presession"
    presession.mkdir(parents=True, exist_ok=True)
    (presession / "composition_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    identity = build_campaign_identity(
        evidence_root=root,
        campaign_commit_sha=commit,
        composition_manifest_sha=manifest["composition_manifest_sha256"],
        nonce=args.nonce,
        live=args.launch_live,
    )
    if args.launch_live:
        reject_presession_live_run_id(identity.run_id)
    run_root = Path(identity.evidence_root)
    for child in ("presession", "live", "postmarket", "per_pr"):
        (run_root / child).mkdir(parents=True, exist_ok=True)
    (run_root / "presession" / "campaign_identity.json").write_text(
        json.dumps(identity.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    wired = _runtime_wired()
    state = "READY_FOR_LIVE_START" if wired else "BLOCKED_BY_RUNTIME_WIRING"
    command = list(args.runtime_command or ["./run_live.sh"])
    launch = {
        "state": state,
        "run_id": identity.run_id,
        "evidence_root": str(run_root),
        "launch_command": f"PYTHONPATH=. {ENABLE_ENV}=true python3 -B scripts/run_unified_live_validation_pr748_756_v1.py --origin-main-sha {args.origin_main_sha} --launch-live",
        "runtime_command": command,
        "campaign_runtime_wired": wired,
        "recorder_instantiated": False,
        "live_observers_registered": wired,
        "single_runtime_process_proven": False,
        "single_websocket_path_proven": False,
        "shutdown_seal_registered": True,
        "presession_run_id_rejected": True,
        "blockers": ([] if wired else ["CURRENT_LAUNCH_COMMAND_DOES_NOT_ACTIVATE_CAMPAIGN"]),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    (run_root / "presession" / "launch_preflight.json").write_text(
        json.dumps(launch, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.launch_live:
        if not wired and command == ["./run_live.sh"]:
            print(json.dumps(launch, indent=2, sort_keys=True))
            return 2
        result = launch_runtime_child(identity, command, cwd=Path("."), timeout_sec=args.timeout_sec)
        launch.update(
            {
                "recorder_instantiated": True,
                "single_runtime_process_proven": result.child_pid is not None,
                "child_pid": result.child_pid,
                "child_exit_code": result.exit_code,
                "artifact_manifest_sha256": result.artifact_manifest_sha256,
                "sealed": result.sealed,
            }
        )
        (run_root / "presession" / "launch_preflight.json").write_text(
            json.dumps(launch, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(launch, indent=2, sort_keys=True))
        return result.exit_code if result.exit_code else (0 if wired else 2)
    print(json.dumps(launch, indent=2, sort_keys=True))
    return 0 if wired else 2


if __name__ == "__main__":
    raise SystemExit(main())
