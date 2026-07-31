"""Governed child-process launcher for the unified campaign.

This module supervises one runtime child process and records process-level
evidence. It does not by itself wire internal TradeBot observers into the
recorder; launch preflight must remain blocked until those call paths exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import subprocess
import sys
import time
from typing import Any, Sequence

from core.unified_live_validation_pr748_756.campaign_contract import (
    COMPOSITION_SHA_ENV,
    ENABLE_ENV,
    EVIDENCE_ROOT_ENV,
    RUN_ID_ENV,
    CampaignIdentity,
    reject_presession_live_run_id,
)
from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
from core.unified_live_validation_pr748_756.seal import seal_evidence_root


@dataclass(frozen=True)
class RuntimeLaunchResult:
    run_id: str
    evidence_root: str
    child_pid: int | None
    exit_code: int
    sealed: bool
    artifact_manifest_sha256: str | None


def build_child_environment(identity: CampaignIdentity, base_env: dict[str, str] | None = None) -> dict[str, str]:
    reject_presession_live_run_id(identity.run_id)
    env = dict(os.environ if base_env is None else base_env)
    env[ENABLE_ENV] = "true"
    env["TRADEBOT_READ_ONLY"] = "true"
    env[RUN_ID_ENV] = identity.run_id
    env[EVIDENCE_ROOT_ENV] = identity.evidence_root
    env[COMPOSITION_SHA_ENV] = identity.composition_manifest_sha
    env["PYTHONUNBUFFERED"] = "1"
    return env


def launch_runtime_child(
    identity: CampaignIdentity,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_sec: float | None = None,
    seal_on_exit: bool = True,
) -> RuntimeLaunchResult:
    reject_presession_live_run_id(identity.run_id)
    recorder = AppendOnlyRecorder(identity)
    root = Path(identity.evidence_root)
    live = root / "live"
    live.mkdir(parents=True, exist_ok=True)
    stdout_path = live / "stdout.log"
    stderr_path = live / "stderr.log"
    env = build_child_environment(identity)
    start = time.time()
    process_identity: dict[str, Any] = {
        "run_id": identity.run_id,
        "parent_pid": os.getpid(),
        "child_pid": None,
        "command": list(command),
        "cwd": str(cwd),
        "start_epoch": start,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    exit_code = 127
    child_pid: int | None = None
    with stdout_path.open("ab") as stdout, stderr_path.open("ab") as stderr:
        try:
            proc = subprocess.Popen(list(command), cwd=str(cwd), env=env, stdout=stdout, stderr=stderr)
            child_pid = proc.pid
            process_identity["child_pid"] = child_pid
            (live / "process_identity.json").write_text(
                json.dumps(process_identity, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            recorder.append(
                "live/heartbeat.jsonl",
                {
                    "source_timestamp": start,
                    "receipt_timestamp": time.time(),
                    "source": "governed_launcher",
                    "event": "child_process_started",
                    "child_pid": child_pid,
                    "feed_session_id": None,
                    "reconnect_generation": None,
                    "symbol": None,
                    "instrument_token": None,
                    "source_provenance_type": "launcher_process_supervision",
                },
                pr_number=750,
            )
            try:
                exit_code = proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.terminate()
                try:
                    exit_code = proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    exit_code = proc.wait()
                recorder.append(
                    "live/exceptions.jsonl",
                    {
                        "source_timestamp": time.time(),
                        "receipt_timestamp": time.time(),
                        "source": "governed_launcher",
                        "event": "child_process_timeout",
                        "timeout_sec": timeout_sec,
                        "feed_session_id": None,
                        "reconnect_generation": None,
                        "symbol": None,
                        "instrument_token": None,
                        "source_provenance_type": "launcher_process_supervision",
                    },
                    pr_number=750,
                )
        except Exception as exc:
            exit_code = 126
            recorder.append(
                "live/exceptions.jsonl",
                {
                    "source_timestamp": time.time(),
                    "receipt_timestamp": time.time(),
                    "source": "governed_launcher",
                    "event": "child_process_launch_failed",
                    "error": f"{type(exc).__name__}:{exc}",
                    "feed_session_id": None,
                    "reconnect_generation": None,
                    "symbol": None,
                    "instrument_token": None,
                    "source_provenance_type": "launcher_process_supervision",
                },
                pr_number=750,
            )
    if exit_code != 0 or list(command) != ["./run_live.sh"]:
        recorder.append(
            "live/feed_truth_samples.jsonl",
            {
                "source_timestamp": time.time(),
                "receipt_timestamp": time.time(),
                "source": "governed_launcher",
                "event": "runtime_feed_source_unavailable_to_smoke"
                if exit_code == 0
                else "runtime_exited_before_feed_truth_sample_verified",
                "blocker": "NON_MARKET_SMOKE_HAS_NO_LIVE_FEED_SOURCE"
                if exit_code == 0
                else "RUNTIME_EXITED_BEFORE_FEED_TRUTH_SAMPLE",
                "feed_session_id": None,
                "reconnect_generation": None,
                "symbol": None,
                "instrument_token": None,
                "source_provenance_type": "launcher_process_supervision",
            },
            pr_number=750,
        )
    (live / "process_identity.json").write_text(
        json.dumps({**process_identity, "child_pid": child_pid, "exit_code": exit_code, "end_epoch": time.time()}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest_sha = None
    sealed = False
    if seal_on_exit:
        manifest = seal_evidence_root(root)
        manifest_sha = str(manifest.get("artifact_manifest_sha256") or "")
        sealed = True
    return RuntimeLaunchResult(
        run_id=identity.run_id,
        evidence_root=str(root),
        child_pid=child_pid,
        exit_code=exit_code,
        sealed=sealed,
        artifact_manifest_sha256=manifest_sha,
    )


def smoke_child_main() -> int:
    payload = {
        "run_id": os.getenv(RUN_ID_ENV),
        "evidence_root": os.getenv(EVIDENCE_ROOT_ENV),
        "composition_sha": os.getenv(COMPOSITION_SHA_ENV),
        "enabled": os.getenv(ENABLE_ENV),
        "read_only": os.getenv("TRADEBOT_READ_ONLY"),
        "pid": os.getpid(),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(smoke_child_main())
