from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
from typing import Any

from research.option_e2e_recertification_v4.ce_pe_history_inventory_v1.build_inventory import (
    build as build_inventory_evidence,
)
from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    build_manifests,
    canonical_json,
    write_json_with_sidecar,
)
from research.option_e2e_recertification_v4.current_certification_source_universe_v1.oracle import (
    recompute_current_universe,
)


class LocalInventoryRunnerError(RuntimeError):
    pass


_ALLOWED_REPLACE_PARENT = Path("/tmp")
_ALLOWED_REPLACE_PREFIX = "tradebot-ce-pe-history-inventory"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_clean_output_root(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if resolved.exists() and (
        not resolved.is_dir() or any(resolved.iterdir())
    ):
        raise LocalInventoryRunnerError(f"output_root_not_empty:{resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def _replace_output_root(path: Path) -> None:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise LocalInventoryRunnerError(f"unsafe_output_delete_symlink:{expanded}")
    resolved = expanded.resolve(strict=True)
    if (
        resolved.parent == resolved
        or not any(part.startswith(_ALLOWED_REPLACE_PREFIX) for part in resolved.parts)
    ):
        raise LocalInventoryRunnerError(f"unsafe_output_delete:{resolved}")
    if not resolved.is_dir():
        raise LocalInventoryRunnerError(f"output_delete_target_not_directory:{resolved}")
    shutil.rmtree(resolved)


def _assert_output_outside_inputs(
    output_root: Path, machine: dict[str, Any]
) -> None:
    for row in machine.get("roots", []):
        root = Path(row["absolute_path"]).resolve(strict=True)
        if (
            output_root == root
            or output_root.is_relative_to(root)
            or root.is_relative_to(output_root)
        ):
            raise LocalInventoryRunnerError(
                f"output_root_overlaps_input:{row['current_root_id']}:"
                f"{output_root}"
            )


def _portable_artifact_hashes(directory: Path) -> dict[str, str]:
    return {
        path.name: _sha256_file(path)
        for path in sorted(directory.iterdir(), key=lambda item: item.name)
        if path.is_file()
    }


def _run_once(
    *, machine_manifest: Path, output_dir: Path
) -> dict[str, Any]:
    return build_inventory_evidence(
        machine_manifest=machine_manifest,
        output_dir=output_dir,
    )


def run(*, campaign_worktree: Path, output_root: Path) -> dict[str, Any]:
    campaign = campaign_worktree.expanduser().resolve(strict=True)
    output = _require_clean_output_root(output_root)

    manifests = build_manifests(campaign_worktree=campaign)
    machine = manifests["machine"]
    portable = manifests["portable"]
    universe_oracle = recompute_current_universe(machine, portable)
    if universe_oracle.get("primary_oracle_agreement") != "AGREEMENT":
        raise LocalInventoryRunnerError(
            "current_source_universe_primary_oracle_disagreement"
        )
    _assert_output_outside_inputs(output, machine)

    manifest_dir = output / "source-universe"
    manifest_dir.mkdir()
    machine_manifest = (
        manifest_dir / "current_source_universe_machine_manifest.json"
    )
    write_json_with_sidecar(machine_manifest, machine)
    write_json_with_sidecar(
        manifest_dir / "current_source_universe_contract.json",
        portable,
    )
    write_json_with_sidecar(
        manifest_dir / "current_source_universe_oracle.json",
        universe_oracle,
    )

    run_a_dir = output / "run-a"
    run_b_dir = output / "run-b"
    summary_a = _run_once(
        machine_manifest=machine_manifest, output_dir=run_a_dir
    )
    summary_b = _run_once(
        machine_manifest=machine_manifest, output_dir=run_b_dir
    )

    hashes_a = _portable_artifact_hashes(run_a_dir)
    hashes_b = _portable_artifact_hashes(run_b_dir)
    deterministic = hashes_a == hashes_b
    if not deterministic:
        raise LocalInventoryRunnerError(
            "run_a_run_b_portable_artifacts_differ"
        )

    valid_dates = sorted(
        set(summary_a.get("valid_option_session_dates", []))
        | set(summary_b.get("valid_option_session_dates", []))
    )
    session_count = len(valid_dates)
    calendar_months = sorted({value[:7] for value in valid_dates})
    coverage_candidate_found = (
        session_count >= 100 and len(calendar_months) >= 6
    )

    final = {
        "schema_version": "ce_pe_history_inventory_local_execution_v1",
        "campaign_worktree_head": next(
            (
                row.get("head")
                for row in machine.get("roots", [])
                if row.get("current_root_id") == "CAMPAIGN_WORKTREE"
            ),
            None,
        ),
        "root_count": machine.get("root_count"),
        "source_universe_oracle": universe_oracle.get(
            "primary_oracle_agreement"
        ),
        "run_a_primary_oracle": summary_a.get(
            "primary_oracle_agreement"
        ),
        "run_b_primary_oracle": summary_b.get(
            "primary_oracle_agreement"
        ),
        "run_a_run_b_byte_determinism": (
            "PASS" if deterministic else "FAIL"
        ),
        "portable_artifact_hashes": hashes_a,
        "files_visited": summary_a.get("files_visited"),
        "parquet_metadata_inspected": summary_a.get(
            "parquet_metadata_inspected"
        ),
        "zip_members_inspected": summary_a.get(
            "zip_members_inspected"
        ),
        "option_candidate_count": summary_a.get(
            "option_candidate_count"
        ),
        "valid_option_session_dates": valid_dates,
        "valid_option_session_count": session_count,
        "calendar_months": calendar_months,
        "calendar_month_count": len(calendar_months),
        "chronological_coverage_verdict": summary_a.get(
            "chronological_coverage_verdict"
        ),
        "minimum_coverage_candidate_sessions": 100,
        "minimum_coverage_candidate_months": 6,
        "coverage_candidate_found": coverage_candidate_found,
        "strategy_development_authorized": False,
        "strategy_authorization_blockers": [
            "contract_availability_review_required",
            "expiry_and_non_expiry_coverage_review_required",
            "chronological_partition_freeze_required",
            "strict_loader_all_selected_contracts_required",
        ],
        "next_decision": (
            "COVERAGE_CANDIDATE_FOUND_REQUIRES_CONTRACT_AND_PARTITION_REVIEW"
            if coverage_candidate_found
            else "MORE_CE_PE_HISTORY_REQUIRED_OR_DEEP_CANDIDATE_REVIEW"
        ),
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json_with_sidecar(
        output / "ce_pe_history_inventory_local_summary.json", final
    )
    return final


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic metadata-first CE/PE history inventory "
            "on Mac-local roots"
        )
    )
    parser.add_argument(
        "--campaign-worktree",
        type=Path,
        default=Path(
            "/Users/madhuram/tradebot-ce-pe-option-certification-v1"
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/tmp/tradebot-ce-pe-history-inventory-v1"),
    )
    parser.add_argument(
        "--replace-output",
        action="store_true",
        help=(
            "Delete only an explicitly named "
            "/tmp/tradebot-ce-pe-history-inventory* directory before running."
        ),
    )
    args = parser.parse_args()

    if args.replace_output and args.output_root.exists():
        _replace_output_root(args.output_root)

    result = run(
        campaign_worktree=args.campaign_worktree,
        output_root=args.output_root,
    )
    print(canonical_json(result), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
