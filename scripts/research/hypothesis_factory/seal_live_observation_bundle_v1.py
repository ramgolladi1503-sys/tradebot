#!/usr/bin/env python3
"""Seal post-close observation artifacts without touching the live producer.

The sealer is research-only. It verifies the producer worktree is clean at an
explicit exact SHA, hashes regular files under an external runtime root, and
writes one immutable-style manifest outside both repositories. It grants no
broker, order, paper, live-execution, or structural-edge authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "tradebot-live-observation-bundle-v1"
KERNEL_BASE_AUTHORITY_SHA = "46dd4f7df9b63486eb633a12baf25412cd4f761d"
ALLOWED_STATES = {"LIVE_PROSPECTIVE", "CAPTURE_THEN_OFFLINE"}
ALLOWED_ROLES = {"PRODUCER_RAW", "READ_ONLY_DERIVED", "DERIVED_MANIFEST"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_sha(value: str, *, field: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise ValueError(f"{field}_EXACT_SHA_REQUIRED")
    return text


def parse_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("OBSERVATION_DATE_INVALID") from exc
    return parsed.isoformat()


def regular_file(path: Path, *, code: str) -> Path:
    resolved = path.expanduser().absolute()
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError(f"{code}_REGULAR_FILE_REQUIRED:{resolved}")
    return resolved.resolve()


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def git_output(worktree: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise ValueError(f"PRODUCER_GIT_CHECK_FAILED:{' '.join(args)}:{completed.stderr.strip()}")
    return completed.stdout.strip()


def verify_producer(worktree: Path, expected_sha: str) -> dict[str, Any]:
    root = worktree.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("PRODUCER_WORKTREE_MISSING")
    actual = exact_sha(git_output(root, "rev-parse", "HEAD"), field="PRODUCER_ACTUAL")
    expected = exact_sha(expected_sha, field="PRODUCER_EXPECTED")
    if actual != expected:
        raise ValueError(f"PRODUCER_SHA_MISMATCH:{actual}:{expected}")
    status = git_output(root, "status", "--porcelain")
    if status:
        raise ValueError("PRODUCER_WORKTREE_DIRTY")
    branch = git_output(root, "branch", "--show-current") or "DETACHED"
    return {"worktree": str(root), "git_sha": actual, "branch": branch, "git_clean": True}


def parse_artifact_spec(spec: str) -> tuple[str, str, str, Path]:
    parts = str(spec).split(":", 3)
    if len(parts) != 4:
        raise ValueError("ARTIFACT_SPEC_INVALID; expected KIND:STATE:ROLE:/absolute/path")
    kind, state, role, raw_path = (part.strip() for part in parts)
    if not kind or not re.fullmatch(r"[A-Z0-9_]+", kind):
        raise ValueError("ARTIFACT_KIND_INVALID")
    if state not in ALLOWED_STATES:
        raise ValueError(f"ARTIFACT_STATE_REJECTED:{state}")
    if role not in ALLOWED_ROLES:
        raise ValueError(f"ARTIFACT_ROLE_REJECTED:{role}")
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        raise ValueError("ARTIFACT_PATH_MUST_BE_ABSOLUTE")
    return kind, state, role, path


def seal_bundle(
    *,
    producer_worktree: Path,
    expected_producer_sha: str,
    runtime_root: Path,
    observation_date: str,
    artifact_specs: Iterable[str],
    output_manifest: Path,
    kernel_repo_root: Path | None = None,
) -> dict[str, Any]:
    obs_date = parse_date(observation_date)
    producer = verify_producer(producer_worktree, expected_producer_sha)
    runtime = runtime_root.expanduser().resolve()
    if not runtime.is_dir():
        raise ValueError("RUNTIME_ROOT_MISSING")
    if is_within(runtime, Path(producer["worktree"])):
        raise ValueError("RUNTIME_ROOT_INSIDE_PRODUCER_REPO")

    kernel_root = (kernel_repo_root or Path(__file__).resolve().parents[3]).resolve()
    output = output_manifest.expanduser().absolute()
    if not output.is_absolute():
        raise ValueError("OUTPUT_PATH_MUST_BE_ABSOLUTE")
    if is_within(output, Path(producer["worktree"])) or is_within(output, kernel_root):
        raise ValueError("OUTPUT_MUST_BE_EXTERNAL_TO_REPOSITORIES")

    artifacts: list[dict[str, Any]] = []
    kinds: set[str] = set()
    paths: set[str] = set()
    for spec in artifact_specs:
        kind, state, role, raw_path = parse_artifact_spec(spec)
        path = regular_file(raw_path, code="ARTIFACT")
        if not is_within(path, runtime):
            raise ValueError(f"ARTIFACT_OUTSIDE_RUNTIME_ROOT:{kind}")
        key = str(path)
        if kind in kinds:
            raise ValueError(f"DUPLICATE_ARTIFACT_KIND:{kind}")
        if key in paths:
            raise ValueError(f"DUPLICATE_ARTIFACT_PATH:{key}")
        kinds.add(kind)
        paths.add(key)
        artifacts.append(
            {
                "evidence_kind": kind,
                "state": state,
                "role": role,
                "path": key,
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
        )
    if not artifacts:
        raise ValueError("ARTIFACTS_REQUIRED")

    payload = {
        "schema": SCHEMA,
        "observation_date": obs_date,
        "sealed_at_utc": datetime.now(timezone.utc).isoformat(),
        "kernel_base_authority_sha": KERNEL_BASE_AUTHORITY_SHA,
        "producer": {
            **producer,
            "source_authentication": "GIT_WORKTREE_EXACT_SHA_AND_CLEAN",
        },
        "runtime_root": str(runtime),
        "artifacts": artifacts,
        "bundle_state": "CAPTURED_NOT_CERTIFIED",
        "missing_value_policy": "PRESERVE_MISSING; NEVER_COERCE_TO_ZERO",
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "structural_edge_certified": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(output, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError("OUTPUT_MANIFEST_ALREADY_EXISTS") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-worktree", required=True)
    parser.add_argument("--expected-producer-sha", required=True)
    parser.add_argument("--runtime-root", required=True)
    parser.add_argument("--observation-date", required=True)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Repeat KIND:STATE:ROLE:/absolute/path",
    )
    parser.add_argument("--output-manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = seal_bundle(
        producer_worktree=Path(args.producer_worktree),
        expected_producer_sha=args.expected_producer_sha,
        runtime_root=Path(args.runtime_root),
        observation_date=args.observation_date,
        artifact_specs=args.artifact,
        output_manifest=Path(args.output_manifest),
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
