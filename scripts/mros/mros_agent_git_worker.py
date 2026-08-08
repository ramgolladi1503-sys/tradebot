#!/usr/bin/env python3
"""Mac-side Git mailbox worker for MROS isolated reviewer/auditor jobs.

Transport is deliberately separated from repository authority:
- requests/results live on automation/mros-agent-queue-v1;
- exact candidate SHAs may point anywhere in the same repository;
- the worker never updates MROS_PROGRAM_STATE or accepts a sprint;
- the authoritative program branch consumes validated output later.

The worker creates one local commit per completed job, rebases that narrow commit
onto the latest remote queue branch, and pushes HEAD:<queue-branch>. This lets the
controller enqueue additional jobs while a model process is running without
turning queue traffic into MROS program-state commits.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from mros_agent_bridge import BridgeError, MrosAgentBridge, load_config

QUEUE_ROOT = Path("research/evidence/sprints/S003/agent_queue")
REQUEST_DIR = QUEUE_ROOT / "requests"
RECEIPT_DIR = QUEUE_ROOT / "receipts"
ALLOWED_JOB_TYPES = {"reviewer", "auditor"}
DEFAULT_QUEUE_BRANCH = "automation/mros-agent-queue-v1"


class WorkerError(RuntimeError):
    pass


def run_git(repo: Path, *args: str, timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode != 0:
        raise WorkerError(f"GIT_COMMAND_FAILED:{' '.join(args)}:{result.stdout.strip()}")
    return result


def ensure_clean(repo: Path) -> None:
    status = run_git(repo, "status", "--porcelain").stdout.strip()
    if status:
        raise WorkerError("QUEUE_WORKTREE_NOT_CLEAN")


def sync_queue(repo: Path, remote_branch: str) -> None:
    ensure_clean(repo)
    run_git(repo, "fetch", "origin", remote_branch, timeout=180)
    run_git(repo, "rebase", f"origin/{remote_branch}", timeout=180)


def list_requests(repo: Path) -> list[Path]:
    directory = repo / REQUEST_DIR
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("*.json") if path.is_file())


def receipt_path(repo: Path, request: Path) -> Path:
    return repo / RECEIPT_DIR / request.name


def validate_request_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise WorkerError("REQUEST_OBJECT_REQUIRED")
    required = {"job_type", "role_id", "candidate_sha", "packet_path", "output_path", "backend"}
    missing = sorted(required - set(payload))
    if missing:
        raise WorkerError("REQUEST_FIELDS_MISSING:" + ",".join(missing))
    if payload.get("job_type") not in ALLOWED_JOB_TYPES:
        raise WorkerError("REQUEST_JOB_TYPE_INVALID")
    allowed_keys = required | {"schema_version", "request_id", "created_by", "created_at"}
    extras = sorted(set(payload) - allowed_keys)
    if extras:
        raise WorkerError("REQUEST_FIELDS_UNKNOWN:" + ",".join(extras))
    return payload


def write_receipt(path: Path, *, request: dict[str, Any], record: dict[str, Any], worker_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "worker_id": worker_id,
        "request": request,
        "job": record,
        "runtime_authority": "NONE",
        "broker_actions_allowed": False,
    }
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def commit_and_push(repo: Path, remote_branch: str, paths: list[Path], message: str) -> str:
    relative = [str(path.relative_to(repo)) for path in paths]
    run_git(repo, "add", "--", *relative)
    staged = run_git(repo, "diff", "--cached", "--name-only").stdout.splitlines()
    if set(staged) != set(relative):
        run_git(repo, "reset")
        raise WorkerError("COMMIT_SCOPE_VIOLATION")
    run_git(repo, "commit", "-m", message)
    # Rebase the narrow evidence commit over any queue requests added while the
    # model was running. Requests/results use distinct immutable paths.
    run_git(repo, "fetch", "origin", remote_branch, timeout=180)
    run_git(repo, "rebase", f"origin/{remote_branch}", timeout=180)
    run_git(repo, "push", "origin", f"HEAD:{remote_branch}", timeout=180)
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()


def process_one(repo: Path, remote_branch: str, bridge: MrosAgentBridge, request_file: Path, worker_id: str) -> dict[str, Any]:
    receipt = receipt_path(repo, request_file)
    if receipt.exists():
        return {"request": request_file.name, "status": "ALREADY_RECEIPTED"}
    request = validate_request_payload(json.loads(request_file.read_text(encoding="utf-8")))
    record = bridge.submit(request)
    while True:
        current = bridge.get(record.job_id)
        if current.state in {"SUCCEEDED", "FAILED", "BLOCKED", "CANCELLED"}:
            break
        time.sleep(2)
    final = current.public_dict()
    write_receipt(receipt, request=request, record=final, worker_id=worker_id)
    if current.state != "SUCCEEDED":
        commit_sha = commit_and_push(
            repo,
            remote_branch,
            [receipt],
            f"mros(S003): record failed isolated {request['role_id']} job [skip ci]",
        )
        return {
            "request": request_file.name,
            "status": current.state,
            "job_id": current.job_id,
            "commit_sha": commit_sha,
        }

    output = repo / request["output_path"]
    if not output.is_file() or output.stat().st_size == 0:
        raise WorkerError("OUTPUT_ARTIFACT_MISSING_BEFORE_COMMIT")
    commit_sha = commit_and_push(
        repo,
        remote_branch,
        [output, receipt],
        f"mros(S003): record isolated {request['role_id']} job output [skip ci]",
    )
    return {"request": request_file.name, "status": "SUCCEEDED", "job_id": current.job_id, "commit_sha": commit_sha}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Git for MROS isolated-agent jobs")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--queue-branch", default=DEFAULT_QUEUE_BRANCH)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--worker-id", default=os.environ.get("HOSTNAME") or "mros-mac-worker")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    repo = config.repo_root
    bridge = MrosAgentBridge(config)
    print(
        json.dumps(
            {
                "status": "WORKER_STARTING",
                "queue_branch": args.queue_branch,
                "worker_id": args.worker_id,
                "health": bridge.health(),
            }
        ),
        flush=True,
    )
    while True:
        try:
            sync_queue(repo, args.queue_branch)
            processed = []
            for request in list_requests(repo):
                if receipt_path(repo, request).exists():
                    continue
                processed.append(process_one(repo, args.queue_branch, bridge, request, args.worker_id))
            print(json.dumps({"status": "POLL_COMPLETE", "processed": processed}, sort_keys=True), flush=True)
        except (BridgeError, WorkerError, subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError) as exc:
            print(
                json.dumps({"status": "WORKER_BLOCKED", "error": f"{type(exc).__name__}:{exc}"}),
                file=sys.stderr,
                flush=True,
            )
            if args.once:
                return 2
        if args.once:
            return 0
        time.sleep(max(5, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
