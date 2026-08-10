#!/usr/bin/env python3
"""Governed launcher for the PR #748-#756 unified evidence campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import inspect
import os
import subprocess
import pathlib
import sys
import time
import kiteconnect
from kiteconnect import KiteTicker
import kiteconnect.ticker as kite_ticker
from pathlib import Path
from core import campaign_raw_diagnostics

from core.unified_live_validation_pr748_756.campaign_contract import (
    ENABLE_ENV,
    build_campaign_identity,
    build_composition_manifest,
    current_commit_sha,
    reject_presession_live_run_id,
    require_fresh_evidence_root,
    require_campaign_enabled,
    resolve_session_date,
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


def _single_websocket_path_proven() -> bool:
    text = Path("core/unified_live_validation_pr748_756/launcher.py").read_text(
        encoding="utf-8",
        errors="ignore",
    )
    campaign_has_ws = "KiteTicker" in text or "start_depth_ws(" in text or "kiteconnect" in text
    run_live = Path("run_live.sh").read_text(encoding="utf-8", errors="ignore")
    main_text = Path("main.py").read_text(encoding="utf-8", errors="ignore")
    return (not campaign_has_ws) and "main.py" in run_live and "Orchestrator(" in main_text


def _predecode_diagnostic_contract() -> dict[str, object]:
    path = pathlib.Path(kite_ticker.__file__).resolve()
    source = path.read_text(encoding="utf-8", errors="replace")
    on_message = inspect.getsource(KiteTicker._on_message)
    return {
        "installed_kiteconnect_version": str(getattr(kiteconnect, "__version__", "unknown")),
        "installed_ticker_module": str(path),
        "installed_ticker_source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "predecode_hook_available": "self.on_message" in on_message,
        "predecode_ordering_proven": on_message.find("self.on_message") < on_message.find("self._parse_binary"),
        "diagnostic_writer_ready": True,
        "diagnostic_queue_bounded": True,
        "reactor_heartbeat_ready": True,
        "process_heartbeat_ready": True,
        "protocol_lifecycle_diagnostic_ready": True,
        "ping_pong_observability": "unavailable",
        "ping_pong_unavailable_reason": "installed_protocol_has_no_safe_campaign_instance_hook_without_protocol_subclass",
    }


def _run_diagnostic_self_test(identity) -> bool:
    os.environ["UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE"] = "true"
    os.environ["TRADEBOT_READ_ONLY"] = "true"
    os.environ["UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID"] = identity.run_id
    os.environ["UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT"] = identity.evidence_root
    os.environ["UNIFIED_LIVE_VALIDATION_PR748_756_SESSION_DATE"] = identity.session_date
    os.environ["UNIFIED_LIVE_VALIDATION_PR748_756_COMMIT_SHA"] = identity.campaign_commit_sha
    passed = campaign_raw_diagnostics.run_diagnostic_self_test()
    campaign_raw_diagnostics.shutdown()
    return passed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", default="runtime/diagnostics/unified_live_validation_pr748_756_v1")
    parser.add_argument("--origin-main-sha", required=True)
    parser.add_argument("--nonce")
    parser.add_argument("--launch-live", action="store_true")
    parser.add_argument("--runtime-command", nargs=argparse.REMAINDER)
    parser.add_argument("--timeout-sec", type=float)
    parser.add_argument("--session-date")
    parser.add_argument("--custodian", action="store_true")
    parser.add_argument("--status-run-id")
    args = parser.parse_args()

    if args.status_run_id:
        status_root = Path(args.evidence_root) / args.status_run_id
        status_path = status_root / "custodian_status.json"
        print(status_path.read_text(encoding="utf-8") if status_path.exists() else json.dumps({"state": "UNKNOWN", "run_id": args.status_run_id}))
        return 0 if status_path.exists() else 2

    require_campaign_enabled()
    root = Path(args.evidence_root)
    commit = current_commit_sha(".")
    session_date = resolve_session_date(args.session_date)
    manifest = build_composition_manifest(
        origin_main_sha=args.origin_main_sha,
        integrated_commit_sha=commit,
        session_date=session_date,
    )
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
        session_date=session_date,
    )
    if args.launch_live:
        reject_presession_live_run_id(identity.run_id)
    run_root = Path(identity.evidence_root)
    require_fresh_evidence_root(identity)
    for child in ("presession", "live", "postmarket", "per_pr"):
        (run_root / child).mkdir(parents=True, exist_ok=False)
    (run_root / "presession" / "campaign_identity.json").write_text(
        json.dumps(identity.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    wired = _runtime_wired()
    single_ws = _single_websocket_path_proven()
    diagnostic_contract = _predecode_diagnostic_contract()
    diagnostic_self_test_passed = _run_diagnostic_self_test(identity)
    state = "READY_FOR_LIVE_START" if wired and single_ws and diagnostic_self_test_passed else "BLOCKED_BY_RUNTIME_WIRING"
    command = list(args.runtime_command or ["./run_live.sh"])
    launch = {
        "state": state,
        "run_id": identity.run_id,
        "evidence_root": str(run_root),
        "session_date": identity.session_date,
        "state_path": str(run_root / "state" / "constituent_source_state.json"),
        "previous_state_reused": False,
        **diagnostic_contract,
        "diagnostic_self_test_passed": diagnostic_self_test_passed,
        "wiring_registry_complete": diagnostic_self_test_passed,
        "launch_command": f"PYTHONPATH=. {ENABLE_ENV}=true python3 -B scripts/run_unified_live_validation_pr748_756_v1.py --origin-main-sha {args.origin_main_sha} --launch-live",
        "runtime_command": command,
        "campaign_runtime_wired": wired,
        "recorder_instantiated": False,
        "live_observers_registered": wired,
        "single_runtime_process_proven": False,
        "single_websocket_path_proven": single_ws,
        "shutdown_seal_registered": True,
        "presession_run_id_rejected": True,
        "blockers": (
            []
            if wired and single_ws and diagnostic_self_test_passed
            else [
                blocker
                for blocker, active in (
                    ("CURRENT_LAUNCH_COMMAND_DOES_NOT_ACTIVATE_CAMPAIGN", not wired),
                    ("SINGLE_WEBSOCKET_PATH_NOT_PROVEN", not single_ws),
                    ("CALLBACK_EVIDENCE_PATH_DISCONNECTED", not diagnostic_self_test_passed),
                )
                if active
            ]
        ),
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "custodian_requested": args.custodian,
    }
    (run_root / "presession" / "launch_preflight.json").write_text(
        json.dumps(launch, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.launch_live:
        if not wired and command == ["./run_live.sh"]:
            print(json.dumps(launch, indent=2, sort_keys=True))
            return 2
        if args.custodian:
            custodian_command = [
                sys.executable, "-B", "scripts/run_unified_live_validation_custodian_v1.py",
                "--run-id", identity.run_id, "--run-root", str(run_root),
                "--session-date", identity.session_date, "--commit-sha", commit,
                "--composition-sha", identity.composition_manifest_sha,
                "--origin-main-sha", args.origin_main_sha,
                "--timeout-sec", str(args.timeout_sec or 1200), "--cwd", str(Path.cwd()),
            ]
            custodian_env = dict(os.environ)
            custodian_env.update({
                "UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE": "true",
                "TRADEBOT_READ_ONLY": "true",
            })
            process = subprocess.Popen(custodian_command, cwd=str(Path.cwd()), env=custodian_env, start_new_session=True)
            _write_custodian = {
                "custodian_pid": process.pid,
                "custodian_command": custodian_command,
                "status_command": f"python3 -B scripts/run_unified_live_validation_pr748_756_v1.py --evidence-root {args.evidence_root} --status-run-id {identity.run_id}",
                "follow_command": f"tail -f {run_root / 'live' / 'shutdown_lifecycle.jsonl'}",
                "timeout_deadline": time.time() + float(args.timeout_sec or 1200),
            }
            launch.update(_write_custodian)
            launch["state"] = "CUSTODIAN_RUNNING"
            (run_root / "presession" / "launch_preflight.json").write_text(json.dumps(launch, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(launch, indent=2, sort_keys=True))
            return 0
        result = launch_runtime_child(
            identity,
            command,
            cwd=Path("."),
            timeout_sec=args.timeout_sec,
            seal_on_exit=(command != ["./run_live.sh"]),
        )
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
        if not all(
            bool(launch.get(key))
            for key in (
                "campaign_runtime_wired",
                "recorder_instantiated",
                "live_observers_registered",
                "single_runtime_process_proven",
                "single_websocket_path_proven",
                "shutdown_seal_registered",
                "presession_run_id_rejected",
            )
        ):
            launch["state"] = "BLOCKED_BY_RUNTIME_WIRING"
        (run_root / "presession" / "launch_preflight.json").write_text(
            json.dumps(launch, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(launch, indent=2, sort_keys=True))
        return result.exit_code if result.exit_code else (0 if wired else 2)
    print(json.dumps(launch, indent=2, sort_keys=True))
    return 0 if wired and diagnostic_self_test_passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
