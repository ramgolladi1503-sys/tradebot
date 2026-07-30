#!/usr/bin/env python3
"""Generate deterministic evidence for Runtime Authority Hardening V1."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Iterable

from core.orchestrator_shadowing_audit import audit_repository_orchestrator
from core.ranking_authority import ranking_authority_payload
from core.runtime_authority_contract import (
    assert_feed_boundary_untouched,
    authority_map_payload,
)


REQUIRED_PATHS = (
    "core/canonical_execution_decision.py",
    "core/runtime_authority_contract.py",
    "core/trade_builder_characterization.py",
    "core/orchestration_stage_pipeline.py",
    "core/ranking_authority.py",
    "core/orchestrator_shadowing_audit.py",
    "core/runtime_hardening_campaign.py",
)


def _git_changed_paths(repo_root: Path, base_ref: str) -> tuple[str, ...]:
    command = [
        "git",
        "-C",
        str(repo_root),
        "diff",
        "--name-only",
        f"{base_ref}...HEAD",
    ]
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )
    return tuple(
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip()
    )


def build_audit_payload(
    repo_root: str | Path,
    *,
    changed_paths: Iterable[str],
    base_ref: str,
) -> dict[str, object]:
    root = Path(repo_root).resolve()
    changed = tuple(sorted(set(str(path) for path in changed_paths)))
    errors: list[str] = []
    warnings: list[str] = []

    try:
        assert_feed_boundary_untouched(changed)
    except AssertionError as exc:
        errors.append(str(exc))

    authority = authority_map_payload()
    errors.extend(str(value) for value in authority["validation_errors"])

    ranking = ranking_authority_payload()
    if not ranking["execution_authority_proven"]:
        warnings.append("execution_ranking_authority_pending_runtime_call_path_proof")

    shadowing = audit_repository_orchestrator(root)
    if shadowing.new_shadowing:
        errors.append(
            "new_orchestrator_truth_shadowing:"
            + ",".join(shadowing.new_shadowing)
        )
    if shadowing.missing_baseline:
        warnings.append(
            "shadowing_baseline_reduced:"
            + ",".join(shadowing.missing_baseline)
        )

    missing_paths = [
        path for path in REQUIRED_PATHS if not (root / path).exists()
    ]
    if missing_paths:
        errors.append("required_hardening_paths_missing:" + ",".join(missing_paths))

    line_counts: dict[str, int] = {}
    for path in ("core/orchestrator.py", "strategies/trade_builder.py"):
        source_path = root / path
        if source_path.exists():
            line_counts[path] = len(
                source_path.read_text(encoding="utf-8").splitlines()
            )

    return {
        "schema_version": 1,
        "campaign": "runtime_authority_hardening_v1",
        "base_ref": base_ref,
        "changed_paths": list(changed),
        "feed_boundary_frozen": not any(
            str(error).startswith("feed_boundary_modified:")
            for error in errors
        ),
        "authority_map": authority,
        "ranking_authority": ranking,
        "orchestrator_truth_shadowing": shadowing.to_payload(),
        "line_counts": line_counts,
        "errors": errors,
        "warnings": warnings,
        "verdict": "PASS_RUNTIME_AUTHORITY_HARDENING_AUDIT"
        if not errors
        else "FAIL_RUNTIME_AUTHORITY_HARDENING_AUDIT",
        "allowed_for_live_execution": False,
        "is_order_action": False,
        "broker_api_called": False,
    }


def _markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Runtime Authority Hardening V1 Audit",
        "",
        f"Verdict: `{payload['verdict']}`",
        "",
        f"- Feed boundary frozen: `{payload['feed_boundary_frozen']}`",
        f"- Allowed for live execution: `{payload['allowed_for_live_execution']}`",
        f"- Broker API called: `{payload['broker_api_called']}`",
        "",
        "## Errors",
        "",
    ]
    errors = list(payload.get("errors") or [])
    lines.extend(f"- {error}" for error in errors)
    if not errors:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = list(payload.get("warnings") or [])
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- none")
    lines.extend(["", "## Changed paths", ""])
    changed = list(payload.get("changed_paths") or [])
    lines.extend(f"- `{path}`" for path in changed)
    if not changed:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument(
        "--changed-paths-file",
        default=None,
        help="Optional newline-delimited changed paths. Uses git diff otherwise.",
    )
    parser.add_argument(
        "--output-json",
        default="runtime/diagnostics/runtime_authority_hardening_v1.json",
    )
    parser.add_argument(
        "--output-markdown",
        default="runtime/diagnostics/runtime_authority_hardening_v1.md",
    )
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if args.changed_paths_file:
        changed_paths = tuple(
            line.strip()
            for line in Path(args.changed_paths_file).read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        )
    else:
        changed_paths = _git_changed_paths(root, args.base_ref)

    payload = build_audit_payload(
        root,
        changed_paths=changed_paths,
        base_ref=args.base_ref,
    )

    json_path = root / args.output_json
    md_path = root / args.output_markdown
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["verdict"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
