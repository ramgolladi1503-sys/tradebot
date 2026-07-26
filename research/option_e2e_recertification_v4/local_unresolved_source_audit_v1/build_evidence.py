from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .oracle import oracle_root_facts, oracle_trace_facts, reconcile_primary_oracle
from .root_scan import RootSpec, parse_root_spec, scan_declared_roots
from .trace_audit import audit_execution_entry_trace


def canonical_json(payload: Any) -> str:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    )


def write_json(path: Path, payload: Any) -> str:
    text = canonical_json(payload)
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n", encoding="utf-8"
    )
    return digest


def build(
    *,
    trace_path: Path,
    root_specs: Sequence[RootSpec],
    output_dir: Path,
    expected_root_count: int = 27,
    expected_trace_sha256: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_primary = audit_execution_entry_trace(
        trace_path, expected_sha256=expected_trace_sha256
    )
    root_primary = scan_declared_roots(
        root_specs, expected_root_count=expected_root_count
    )
    trace_oracle = oracle_trace_facts(
        trace_path, expected_sha256=expected_trace_sha256
    )
    root_oracle = oracle_root_facts(
        root_specs, expected_root_count=expected_root_count
    )
    agreement = reconcile_primary_oracle(
        trace_primary, root_primary, trace_oracle, root_oracle
    )
    if agreement["status"] != "AGREEMENT":
        raise RuntimeError("local_source_primary_oracle_disagreement")

    trace_sha = write_json(output_dir / "local_execution_trace_audit.json", trace_primary)
    root_sha = write_json(output_dir / "local_root_census.json", root_primary)
    oracle_payload = {
        "schema_version": "local_unresolved_source_audit_v1",
        "trace": trace_oracle,
        "roots": root_oracle,
        "primary_oracle_agreement": agreement,
    }
    oracle_sha = write_json(output_dir / "local_source_audit_oracle.json", oracle_payload)

    decision = (
        "LOCAL_SOURCE_CANDIDATES_FOUND_REQUIRES_HUMAN_AUTHORITY_REVIEW"
        if root_primary["source_candidate_count"]
        else "LOCAL_SOURCE_AUDIT_COMPLETE_NO_ADDITIONAL_CANDIDATES"
    )
    summary = {
        "schema_version": "local_unresolved_source_audit_v1",
        "decision": decision,
        "source_search_completion": "COMPLETE_DECLARED_ROOTS_INSPECTED",
        "trace_candidate_id": trace_primary["candidate_id"],
        "trace_sha256": trace_primary["trace_sha256"],
        "trace_record_count": trace_primary["record_count"],
        "trace_source_disposition": trace_primary["source_disposition"],
        "declared_root_count": root_primary["declared_root_count"],
        "source_candidate_count": root_primary["source_candidate_count"],
        "exact_duplicate_group_count": root_primary["exact_duplicate_group_count"],
        "remaining_uninspected_known_source_count": 0,
        "authority_candidate_review_required": bool(
            root_primary["source_candidate_count"]
        ),
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "replacement_signal_ledger_required": True,
        "primary_oracle_agreement": agreement["status"],
        "outcome_or_pnl_fields_present": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    summary_sha = write_json(output_dir / "local_source_audit_summary.json", summary)
    manifest = {
        "schema_version": "local_unresolved_source_audit_v1",
        "artifacts": {
            "local_execution_trace_audit.json": trace_sha,
            "local_root_census.json": root_sha,
            "local_source_audit_oracle.json": oracle_sha,
            "local_source_audit_summary.json": summary_sha,
        },
        "trace_sha256": trace_primary["trace_sha256"],
        "all_file_identity_manifest_sha256": root_primary[
            "all_file_identity_manifest_sha256"
        ],
        "candidate_identity_manifest_sha256": root_primary[
            "candidate_identity_manifest_sha256"
        ],
        "primary_oracle_agreement": agreement["status"],
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(output_dir / "external_evidence_manifest.json", manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stream-audit the remaining execution trace and exhaust exactly the "
            "declared local source roots without candidate truncation."
        )
    )
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--root", action="append", required=True)
    parser.add_argument("--expected-root-count", type=int, default=27)
    parser.add_argument("--expected-trace-sha256")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root_specs = [parse_root_spec(value) for value in args.root]
    summary = build(
        trace_path=args.trace,
        root_specs=root_specs,
        output_dir=args.output_dir,
        expected_root_count=args.expected_root_count,
        expected_trace_sha256=args.expected_trace_sha256,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
