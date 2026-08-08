#!/usr/bin/env python3
"""Retry failed isolated S003 bootstrap jobs without overwriting evidence.

A frozen reviewer/auditor role may have multiple transport attempts. Failed
attempts remain committed. A retry gets unique packet/request/result/receipt
paths and the same frozen role/candidate. Only successful attempts can satisfy
quorum. This script never changes authority state.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

QUEUE = "automation/mros-agent-queue-v1"
ROOT = Path("research/evidence/sprints/S003/agent_queue")
REQUESTS = ROOT / "requests"
MAX_ATTEMPTS = 3
MANIFESTS = (
    ROOT / "manifests/S003_R002_REVIEW_POPULATION.json",
    ROOT / "manifests/S003_A001_AUDIT_POPULATION.json",
)


class RetryError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    p = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if check and p.returncode != 0:
        raise RetryError(f"GIT_FAILED:{' '.join(args)}:{(p.stderr or p.stdout).strip()}")
    return p.stdout.strip()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def receipt_for_request(request_path: Path) -> Path:
    return request_path.parents[1] / "receipts" / request_path.name


def successful_attempt(request_path: Path, payload: dict[str, Any]) -> bool:
    receipt = receipt_for_request(request_path)
    output = request_path.parents[1] / "results" / Path(str(payload.get("output_path", ""))).name
    if not receipt.is_file() or not output.is_file() or output.stat().st_size == 0:
        return False
    try:
        rec = read_json(receipt)
    except Exception:
        return False
    job = rec.get("job") if isinstance(rec, dict) else None
    return isinstance(job, dict) and job.get("state") == "SUCCEEDED" and job.get("exit_code") == 0


def failed_attempt(request_path: Path) -> bool:
    receipt = receipt_for_request(request_path)
    if not receipt.is_file():
        return False
    try:
        rec = read_json(receipt)
    except Exception:
        return True
    job = rec.get("job") if isinstance(rec, dict) else None
    return not (isinstance(job, dict) and job.get("state") == "SUCCEEDED" and job.get("exit_code") == 0)


def attempts_for_role(queue_repo: Path, *, role_id: str, candidate: str, job_type: str) -> list[tuple[Path, dict[str, Any]]]:
    attempts: list[tuple[Path, dict[str, Any]]] = []
    request_dir = queue_repo / REQUESTS
    if not request_dir.is_dir():
        return attempts
    for path in sorted(request_dir.glob("*.json")):
        try:
            payload = read_json(path)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("role_id") != role_id or payload.get("candidate_sha") != candidate or payload.get("job_type") != job_type:
            continue
        attempts.append((path, payload))
    return attempts


def retry_paths(root: Path, base_name: str, retry_no: int) -> tuple[str, str, str]:
    stem = Path(base_name).stem
    suffix = f"{stem}_RETRY{retry_no}"
    packet = (root / "packets" / f"{suffix}.md").as_posix()
    output = (root / "results" / f"{suffix}.json").as_posix()
    request = (root / "requests" / f"{suffix}.json").as_posix()
    return packet, output, request


def enqueue_retry(queue_repo: Path, *, original_request: dict[str, Any], original_packet: Path, retry_no: int) -> list[str]:
    base_output = Path(str(original_request["output_path"])).name
    packet_rel, output_rel, request_rel = retry_paths(ROOT, base_output, retry_no)
    packet_path = queue_repo / packet_rel
    request_path = queue_repo / request_rel
    if packet_path.exists() or request_path.exists():
        return []

    original_text = original_packet.read_text(encoding="utf-8")
    retry_text = (
        original_text
        + f"\n\n## Transport retry\nThis is infrastructure retry attempt {retry_no}. "
          "The frozen semantic role and candidate are unchanged. Do not read peer conclusions.\n"
    )
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(retry_text, encoding="utf-8")

    request = dict(original_request)
    request["request_id"] = f"{original_request.get('request_id', 'mros-job')}-retry{retry_no}"
    request["created_by"] = "mros-autonomous-supervisor-retry"
    request["packet_path"] = packet_rel
    request["output_path"] = output_rel
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return [packet_rel, request_rel]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authority-repo", required=True, type=Path)  # interface compatibility; unused
    ap.add_argument("--queue-repo", required=True, type=Path)
    ns = ap.parse_args()
    q = ns.queue_repo.resolve()

    git(q, "fetch", "origin", QUEUE)
    if git(q, "status", "--porcelain"):
        return 3
    git(q, "rebase", f"origin/{QUEUE}")

    created: list[str] = []
    exhausted: list[str] = []
    for manifest_rel in MANIFESTS:
        manifest_path = q / manifest_rel
        if not manifest_path.is_file():
            continue
        manifest = read_json(manifest_path)
        if not isinstance(manifest, dict):
            raise RetryError(f"MANIFEST_INVALID:{manifest_rel}")
        candidate = manifest.get("candidate_head")
        job_type = manifest.get("job_type")
        if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate):
            raise RetryError(f"MANIFEST_CANDIDATE_INVALID:{manifest_rel}")
        if job_type not in {"reviewer", "auditor"}:
            raise RetryError(f"MANIFEST_JOB_TYPE_INVALID:{manifest_rel}")

        for member in manifest.get("members", []):
            if not isinstance(member, dict):
                continue
            role_id = member.get("execution_role_id")
            if not isinstance(role_id, str):
                continue
            attempts = attempts_for_role(q, role_id=role_id, candidate=candidate, job_type=job_type)
            if any(successful_attempt(path, payload) for path, payload in attempts):
                continue
            # A live attempt has no receipt yet; let it finish.
            if any(not receipt_for_request(path).is_file() for path, _ in attempts):
                continue
            failed = [(path, payload) for path, payload in attempts if failed_attempt(path)]
            if not failed:
                continue
            if len(attempts) >= MAX_ATTEMPTS:
                exhausted.append(f"{manifest.get('round')}:{role_id}")
                continue
            original_path, original = attempts[0]
            original_packet = q / str(original["packet_path"])
            if not original_packet.is_file():
                raise RetryError(f"ORIGINAL_PACKET_MISSING:{role_id}")
            files = enqueue_retry(
                q,
                original_request=original,
                original_packet=original_packet,
                retry_no=len(attempts),
            )
            created.extend(files)

    if exhausted:
        raise RetryError("INFRA_RETRY_EXHAUSTED:" + ",".join(sorted(exhausted)))
    if not created:
        return 3

    git(q, "add", "--", *created)
    staged = set(git(q, "diff", "--cached", "--name-only").splitlines())
    if staged != set(created):
        git(q, "reset")
        raise RetryError("RETRY_COMMIT_SCOPE_VIOLATION")
    git(q, "commit", "-m", "mros(S003): enqueue bounded infrastructure retries [skip ci]")
    git(q, "fetch", "origin", QUEUE)
    git(q, "rebase", f"origin/{QUEUE}")
    git(q, "push", "origin", f"HEAD:{QUEUE}")
    print(json.dumps({"status": "RETRIES_QUEUED", "files": created}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
