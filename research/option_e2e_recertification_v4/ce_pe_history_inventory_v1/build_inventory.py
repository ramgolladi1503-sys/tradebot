from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import (
    write_json_with_sidecar,
)
from .inventory import OPTION_CLASSES, build_inventory
from .oracle import oracle_inventory


class OutputDirectoryNotEmptyError(ValueError):
    pass


def _prepare_output(path: Path) -> Path:
    resolved = path.expanduser().resolve(strict=False)
    if resolved.exists():
        if not resolved.is_dir() or any(resolved.iterdir()):
            raise OutputDirectoryNotEmptyError(f"output_directory_not_empty:{resolved}")
    else:
        resolved.mkdir(parents=True, exist_ok=False)
    return resolved


def _coverage_verdict(session_count: int) -> str:
    if session_count == 0:
        return "NO_VALID_OPTION_SESSIONS"
    if session_count == 1:
        return "ONE_SESSION_SMOKE_ONLY"
    if session_count < 20:
        return "MULTI_SESSION_ADAPTER_VALIDATION_ONLY"
    return "DEVELOPMENT_ONLY_COVERAGE"


def _sanitize_primary_session_dates(primary: dict[str, Any]) -> list[str]:
    authoritative: set[str] = set()
    for row in primary.get("candidates", []):
        if row.get("candidate_class") not in OPTION_CLASSES:
            continue
        footer = row.get("parquet_footer") or {}
        minimum = footer.get("footer_date_min")
        maximum = footer.get("footer_date_max")
        footer_dates = {value for value in (minimum, maximum) if value}
        if len(footer_dates) == 1:
            dates = sorted(footer_dates)
            evidence = "PARQUET_FOOTER_STATISTICS"
        elif footer_dates:
            dates = []
            evidence = "MULTI_DATE_FOOTER_REQUIRES_DEEP_REVIEW"
        elif row.get("session_date_evidence") == "PATH_HINT_ONLY":
            dates = list(row.get("session_dates", []))
            evidence = "PATH_HINT_ONLY"
        else:
            dates = []
            evidence = "NOT_ESTABLISHED"
        row["session_dates"] = dates
        row["session_date_evidence"] = evidence
        authoritative.update(dates)
    primary["valid_option_session_dates"] = sorted(authoritative)
    primary["valid_option_session_count"] = len(authoritative)
    return primary["valid_option_session_dates"]


def build(*, machine_manifest: Path, output_dir: Path) -> dict[str, Any]:
    output = _prepare_output(output_dir)
    primary = build_inventory(machine_manifest)
    primary_session_dates = _sanitize_primary_session_dates(primary)
    oracle = oracle_inventory(machine_manifest)
    primary_option_ids = sorted(
        row["candidate_id"]
        for row in primary["candidates"]
        if row.get("candidate_class") in OPTION_CLASSES
    )
    primary_option_manifest = hashlib.sha256(
        "".join(f"{candidate_id}\n" for candidate_id in primary_option_ids).encode(
            "utf-8"
        )
    ).hexdigest()
    checks = {
        "candidate_identity_set": primary_option_ids == oracle["candidate_ids"],
        "candidate_identity_manifest": primary_option_manifest
        == oracle["candidate_identity_manifest_sha256"],
        "session_date_set": primary_session_dates == oracle["session_dates"],
        "files_visited": primary["files_visited"] == oracle["files_visited"],
        "parquet_metadata_inspected": primary["parquet_metadata_inspected"]
        == oracle["parquet_metadata_inspected"],
        "zip_members_inspected": primary["zip_members_inspected"]
        == oracle["zip_members_inspected"],
        "denied_metadata_only_count": primary["denied_metadata_only_count"]
        == oracle["denied_metadata_only_count"],
        "safety": all(
            primary[key] is False
            for key in (
                "outcomes_read",
                "pnl_read",
                "holdout_outcomes_read",
                "strategy_code_invoked",
                "backtests_run",
            )
        ),
    }
    agreement = "AGREEMENT" if all(checks.values()) else "DISAGREEMENT"
    session_dates = primary_session_dates if agreement == "AGREEMENT" else []
    coverage = _coverage_verdict(len(session_dates))
    summary = {
        "schema_version": "ce_pe_history_inventory_summary_v1",
        "decision": "METADATA_FIRST_OPTION_HISTORY_INVENTORY_COMPLETE"
        if agreement == "AGREEMENT"
        else "INVALID_OPTION_HISTORY_INVENTORY_EVIDENCE",
        "primary_oracle_agreement": agreement,
        "reconciliation_checks": checks,
        "root_count": primary["root_count"],
        "files_visited": primary["files_visited"],
        "parquet_files_found": primary["parquet_files_found"],
        "parquet_metadata_inspected": primary["parquet_metadata_inspected"],
        "zip_files_inspected": primary["zip_files_inspected"],
        "zip_members_inspected": primary["zip_members_inspected"],
        "option_candidate_count": len(primary_option_ids),
        "candidate_limit": None,
        "valid_option_session_dates": session_dates,
        "valid_option_session_count": len(session_dates),
        "chronological_coverage_verdict": coverage,
        "minimum_strategy_authorization_sessions": 100,
        "strategy_development_authorized": False,
        "next_gate": "LOCAL_EXTERNAL_ROOT_EXECUTION_REQUIRED",
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "strategy_code_invoked": False,
        "backtests_run": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    primary_sha = write_json_with_sidecar(
        output / "ce_pe_history_inventory.json", primary
    )
    oracle_sha = write_json_with_sidecar(
        output / "ce_pe_history_inventory_oracle.json", oracle
    )
    summary_sha = write_json_with_sidecar(
        output / "ce_pe_history_inventory_summary.json", summary
    )
    external = {
        "schema_version": "ce_pe_history_inventory_external_manifest_v1",
        "artifacts": {
            "ce_pe_history_inventory.json": primary_sha,
            "ce_pe_history_inventory_oracle.json": oracle_sha,
            "ce_pe_history_inventory_summary.json": summary_sha,
        },
        "primary_oracle_agreement": agreement,
        "strategy_development_authorized": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    write_json_with_sidecar(
        output / "ce_pe_history_inventory_external_manifest.json", external
    )
    if agreement != "AGREEMENT":
        raise RuntimeError("ce_pe_history_inventory_primary_oracle_disagreement")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Metadata-first CE/PE history inventory"
    )
    parser.add_argument("--machine-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build(
        machine_manifest=args.machine_manifest, output_dir=args.output_dir
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
