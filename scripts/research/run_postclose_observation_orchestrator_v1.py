#!/usr/bin/env python3
"""Run post-close evidence reconciliation and kernel ingestion without touching live execution.

This orchestration is deliberately detached from the frozen market-hours producer.
It consumes files that already exist after capture. It verifies exact clean Git
worktrees for the producer and validation tools, runs only allow-listed read-only
validators, preserves missing stages as UNKNOWN, and writes a provenance report
under an external runtime root.

It never starts a broker client, websocket/feed owner, or trading process and it
grants no broker, order, paper, live, execution, prospective, or structural-edge
authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = "tradebot-postclose-observation-orchestrator-v1"
FROZEN_PRODUCER_SHA = "f0f5b3d3659415ab36662291e91b8f57fd8d1e07"
SUBSCRIPTION_TOOL_SHA = "21f95a8b5908a8f6b9a0d7bbf459877efed41262"
KERNEL_TOOL_SHA = "10d2f68b08026a269e9c25095bebca683ada67e5"
KERNEL_BASE_SHA = "46dd4f7df9b63486eb633a12baf25412cd4f761d"

SUBSCRIPTION_REL = Path("scripts/validate_subscription_reconciliation_postclose_v1.py")
SEALER_REL = Path("scripts/research/hypothesis_factory/seal_live_observation_bundle_v1.py")
INGESTOR_REL = Path("scripts/research/hypothesis_factory/ingest_live_observation_evidence_v1.py")


class OrchestrationError(ValueError):
    pass


def _exact_sha(value: str, field: str) -> str:
    text = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{40}", text):
        raise OrchestrationError(f"{field}_EXACT_SHA_REQUIRED")
    return text


def _parse_date(value: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise OrchestrationError("OBSERVATION_DATE_INVALID") from exc


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _regular_file(path: Path, code: str) -> Path:
    expanded = path.expanduser().absolute()
    if expanded.is_symlink() or not expanded.is_file():
        raise OrchestrationError(f"{code}_REGULAR_FILE_REQUIRED:{expanded}")
    return expanded.resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(worktree: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OrchestrationError(f"GIT_CHECK_FAILED:{worktree}:{' '.join(args)}")
    return result.stdout.strip()


def verify_clean_worktree(worktree: Path, expected_sha: str, label: str) -> dict[str, Any]:
    root = worktree.expanduser().resolve()
    if not root.is_dir():
        raise OrchestrationError(f"{label}_WORKTREE_MISSING")
    expected = _exact_sha(expected_sha, f"{label}_EXPECTED")
    actual = _exact_sha(_git_output(root, "rev-parse", "HEAD"), f"{label}_ACTUAL")
    if actual != expected:
        raise OrchestrationError(f"{label}_SHA_MISMATCH:{actual}:{expected}")
    if _git_output(root, "status", "--porcelain"):
        raise OrchestrationError(f"{label}_WORKTREE_DIRTY")
    return {
        "worktree": str(root),
        "git_sha": actual,
        "git_clean": True,
        "branch": _git_output(root, "branch", "--show-current") or "DETACHED",
    }


def _tool_path(worktree: Path, relative: Path, code: str) -> Path:
    path = _regular_file(worktree / relative, code)
    if not _is_within(path, worktree):
        raise OrchestrationError(f"{code}_PATH_ESCAPE")
    return path


def _run(argv: list[str], stage: str) -> dict[str, Any]:
    result = subprocess.run(argv, check=False, capture_output=True, text=True)
    record = {
        "stage": stage,
        "argv": argv,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-8000:],
        "stderr_tail": result.stderr[-8000:],
    }
    if result.returncode != 0:
        raise OrchestrationError(f"{stage}_FAILED_RC_{result.returncode}:{json.dumps(record, sort_keys=True)}")
    return record


def _artifact_record(path: Path) -> dict[str, Any]:
    resolved = _regular_file(path, "ARTIFACT")
    return {"path": str(resolved), "sha256": _sha256(resolved), "size_bytes": resolved.stat().st_size}


def _write_once(path: Path, payload: dict[str, Any]) -> None:
    target = path.expanduser().absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise OrchestrationError("REPORT_ALREADY_EXISTS") from exc
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())


def orchestrate(
    *,
    producer_worktree: Path,
    runtime_root: Path,
    observation_date: str,
    subscription_worktree: Path,
    kernel_worktree: Path,
    subscription_inputs: Iterable[Path],
    artifact_specs: Iterable[str],
    report_path: Path,
) -> dict[str, Any]:
    obs_date = _parse_date(observation_date)
    runtime = runtime_root.expanduser().resolve()
    if not runtime.is_dir():
        raise OrchestrationError("RUNTIME_ROOT_MISSING")

    authorities = {
        "producer": verify_clean_worktree(producer_worktree, FROZEN_PRODUCER_SHA, "PRODUCER"),
        "subscription_tool": verify_clean_worktree(subscription_worktree, SUBSCRIPTION_TOOL_SHA, "SUBSCRIPTION_TOOL"),
        "kernel_tool": verify_clean_worktree(kernel_worktree, KERNEL_TOOL_SHA, "KERNEL_TOOL"),
    }
    for name, authority in authorities.items():
        if _is_within(runtime, Path(authority["worktree"])):
            raise OrchestrationError(f"RUNTIME_ROOT_INSIDE_{name.upper()}_REPO")

    report_abs = report_path.expanduser().absolute()
    if not _is_within(report_abs, runtime):
        raise OrchestrationError("REPORT_MUST_BE_INSIDE_EXTERNAL_RUNTIME_ROOT")
    for authority in authorities.values():
        if _is_within(report_abs, Path(authority["worktree"])):
            raise OrchestrationError("REPORT_MUST_BE_EXTERNAL_TO_REPOSITORIES")

    sub_script = _tool_path(subscription_worktree, SUBSCRIPTION_REL, "SUBSCRIPTION_SCRIPT")
    sealer = _tool_path(kernel_worktree, SEALER_REL, "SEALER_SCRIPT")
    ingestor = _tool_path(kernel_worktree, INGESTOR_REL, "INGESTOR_SCRIPT")

    stage_dir = runtime / "postclose_orchestration_v1" / obs_date
    stage_dir.mkdir(parents=True, exist_ok=True)
    sub_output = stage_dir / "subscription_reconciliation.json"
    bundle_manifest = stage_dir / "live_observation_bundle.json"
    ingestion_output = stage_dir / "kernel_ingestion.json"

    stages: dict[str, Any] = {}
    supplied_sub = [Path(p) for p in subscription_inputs]
    if supplied_sub:
        normalized = [_regular_file(path, "SUBSCRIPTION_INPUT") for path in supplied_sub]
        for path in normalized:
            if not _is_within(path, runtime):
                raise OrchestrationError("SUBSCRIPTION_INPUT_OUTSIDE_RUNTIME_ROOT")
        if sub_output.exists():
            raise OrchestrationError("SUBSCRIPTION_OUTPUT_ALREADY_EXISTS")
        stages["subscription_reconciliation"] = _run(
            [sys.executable, str(sub_script), *map(str, normalized), "--output", str(sub_output)],
            "SUBSCRIPTION_RECONCILIATION",
        )
        stages["subscription_reconciliation"]["output"] = _artifact_record(sub_output)
    else:
        stages["subscription_reconciliation"] = {
            "status": "UNKNOWN_NOT_SUPPLIED",
            "reason": "No subscription truth snapshot inputs were supplied; absence is not converted to PASS.",
        }

    specs = list(artifact_specs)
    if specs:
        if bundle_manifest.exists() or ingestion_output.exists():
            raise OrchestrationError("KERNEL_STAGE_OUTPUT_ALREADY_EXISTS")
        seal_argv = [
            sys.executable,
            str(sealer),
            "--producer-worktree", str(producer_worktree.expanduser().resolve()),
            "--expected-producer-sha", FROZEN_PRODUCER_SHA,
            "--runtime-root", str(runtime),
            "--observation-date", obs_date,
        ]
        for spec in specs:
            seal_argv.extend(["--artifact", spec])
        seal_argv.extend(["--output-manifest", str(bundle_manifest)])
        stages["bundle_seal"] = _run(seal_argv, "BUNDLE_SEAL")
        stages["bundle_seal"]["output"] = _artifact_record(bundle_manifest)

        stages["kernel_ingestion"] = _run(
            [
                sys.executable,
                str(ingestor),
                "--bundle-manifest", str(bundle_manifest),
                "--expected-producer-sha", FROZEN_PRODUCER_SHA,
                "--observation-date", obs_date,
                "--output-record", str(ingestion_output),
            ],
            "KERNEL_INGESTION",
        )
        stages["kernel_ingestion"]["output"] = _artifact_record(ingestion_output)
    else:
        stages["bundle_seal"] = {
            "status": "UNKNOWN_NOT_SUPPLIED",
            "reason": "No H1/CAS artifact specs were supplied; absence is not converted to PASS.",
        }
        stages["kernel_ingestion"] = {
            "status": "UNKNOWN_NOT_RUN",
            "reason": "Kernel ingestion requires a sealed bundle from supplied artifacts.",
        }

    report = {
        "schema": SCHEMA,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "observation_date": obs_date,
        "runtime_root": str(runtime),
        "authorities": authorities,
        "expected_authority": {
            "frozen_producer_sha": FROZEN_PRODUCER_SHA,
            "subscription_tool_sha": SUBSCRIPTION_TOOL_SHA,
            "kernel_tool_sha": KERNEL_TOOL_SHA,
            "kernel_base_sha": KERNEL_BASE_SHA,
        },
        "stages": stages,
        "artifact_inputs": [str(spec) for spec in specs],
        "broker_write_authority": False,
        "order_authority": False,
        "paper_authorized": False,
        "live_authorized": False,
        "execution_viable": False,
        "prospective_supported": False,
        "structural_edge_certified": False,
        "interpretation": (
            "This report proves only the exact-SHA post-close orchestration steps that actually ran. "
            "UNKNOWN stages remain UNKNOWN. It does not create live/prospective evidence or certify an edge."
        ),
    }
    _write_once(report_abs, report)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--producer-worktree", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--observation-date", required=True)
    parser.add_argument("--subscription-worktree", required=True, type=Path)
    parser.add_argument("--kernel-worktree", required=True, type=Path)
    parser.add_argument("--subscription-input", action="append", default=[], type=Path)
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        help="Repeat the kernel sealer contract: KIND:STATE:ROLE:/absolute/path",
    )
    parser.add_argument("--report", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = orchestrate(
        producer_worktree=args.producer_worktree,
        runtime_root=args.runtime_root,
        observation_date=args.observation_date,
        subscription_worktree=args.subscription_worktree,
        kernel_worktree=args.kernel_worktree,
        subscription_inputs=args.subscription_input,
        artifact_specs=args.artifact,
        report_path=args.report,
    )
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
