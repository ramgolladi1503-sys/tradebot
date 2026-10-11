from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from .oracle import oracle_root_facts, oracle_trace_facts, reconcile_primary_oracle
from .root_scan import RootSpec, parse_root_spec, scan_declared_roots
from .trace_audit import audit_execution_entry_trace


class OutputDirectoryInsideDeclaredRootError(ValueError):
    """Evidence output must not mutate any directory being audited."""


class OutputDirectoryNotEmptyError(ValueError):
    """Evidence output must start absent or empty to exclude stale artifacts."""


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


def write_reconciliation_diagnostic(
    path: Path,
    *,
    agreement: dict[str, Any],
    trace_primary: dict[str, Any],
    root_primary: dict[str, Any],
    trace_oracle: dict[str, Any],
    root_oracle: dict[str, Any],
    input_snapshot_identity: dict[str, Any] | None = None,
) -> str:
    def safe_value(payload: dict[str, Any], key: str) -> Any:
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, list):
            return {"type": "list", "count": len(value)}
        if isinstance(value, dict):
            return {"type": "dict", "keys": sorted(map(str, value.keys()))}
        return str(type(value).__name__)

    trace_map = {
        "trace_sha256": "trace_sha256",
        "trace_size_bytes": "trace_size_bytes",
        "trace_record_count": "record_count",
        "trace_blank_line_count": "blank_line_count",
        "trace_first_timestamp": "first_timestamp_utc",
        "trace_last_timestamp": "last_timestamp_utc",
        "trace_semantic_stream": "semantic_record_stream_sha256",
        "trace_key_manifest": "key_path_manifest_sha256",
    }
    root_map = {
        "root_count": "declared_root_count",
        "root_file_count": "total_file_count",
        "root_directory_count": "total_directory_count",
        "root_excluded_directory_names": "excluded_directory_names",
        "root_excluded_directory_count": "excluded_directory_count",
        "root_excluded_directory_manifest": "excluded_directory_path_manifest_sha256",
        "root_candidate_count": "source_candidate_count",
        "root_denied_candidate_count": "denied_outcome_or_pnl_candidate_count",
        "root_candidate_id_manifest": "candidate_id_manifest_sha256",
        "root_all_file_manifest": "all_file_identity_manifest_sha256",
        "root_candidate_content_manifest": "candidate_identity_manifest_sha256",
        "scan_complete": "scan_complete",
    }
    checks: list[dict[str, Any]] = []
    for check_name, key in trace_map.items():
        primary = safe_value(trace_primary, key)
        oracle = safe_value(trace_oracle, key)
        checks.append(
            {
                "check": check_name,
                "passed": primary == oracle,
                "primary_value": primary,
                "oracle_value": oracle,
                "value_type": type(primary).__name__,
            }
        )
    for check_name, key in root_map.items():
        primary_key = "candidate_identity_manifest_sha256" if check_name == "root_candidate_content_manifest" else key
        primary = safe_value(root_primary, primary_key)
        oracle = safe_value(root_oracle, key)
        checks.append(
            {
                "check": check_name,
                "passed": primary == oracle,
                "primary_value": primary,
                "oracle_value": oracle,
                "value_type": type(primary).__name__,
            }
        )
    for check_name in ("outcome_boundary", "safety"):
        value = agreement.get("checks", {}).get(check_name)
        checks.append(
            {
                "check": check_name,
                "passed": bool(value),
                "primary_value": bool(value),
                "oracle_value": bool(value),
                "value_type": "bool",
            }
        )
    diagnostic = {
        "schema_version": "local_source_reconciliation_diagnostic_v1",
        "reconciliation_status": agreement.get("status"),
        "checks": checks,
        "input_snapshot_identity": input_snapshot_identity or {},
        "absolute_paths_published": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    return write_json(path, diagnostic)


def load_root_manifest(path: Path) -> list[RootSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    roots = payload.get("roots")
    if not isinstance(roots, list):
        raise ValueError("root_manifest_missing_roots")
    specs: list[RootSpec] = []
    for root in roots:
        if not isinstance(root, dict):
            raise ValueError("root_manifest_root_not_object")
        root_id = root.get("current_root_id") or root.get("root_id")
        root_path = root.get("absolute_path") or root.get("path")
        if not isinstance(root_id, str) or not isinstance(root_path, str):
            raise ValueError("root_manifest_root_missing_id_or_path")
        specs.append(parse_root_spec(f"{root_id}={root_path}"))
    return specs


def _prepare_output_directory(
    output_dir: Path, root_specs: Sequence[RootSpec]
) -> Path:
    resolved_output = output_dir.expanduser().resolve(strict=False)
    for spec in root_specs:
        resolved_root = spec.path.expanduser().resolve(strict=True)
        if resolved_output == resolved_root or resolved_output.is_relative_to(resolved_root):
            raise OutputDirectoryInsideDeclaredRootError(
                f"output_directory_inside_declared_root:root_id={spec.root_id}"
            )
    if resolved_output.exists():
        if not resolved_output.is_dir() or any(resolved_output.iterdir()):
            raise OutputDirectoryNotEmptyError(
                f"output_directory_not_empty:{resolved_output}"
            )
    else:
        resolved_output.mkdir(parents=True, exist_ok=False)
    return resolved_output


def build(
    *,
    trace_path: Path,
    root_specs: Sequence[RootSpec],
    output_dir: Path,
    expected_root_count: int = 27,
    expected_trace_sha256: str | None = None,
) -> dict[str, Any]:
    resolved_output = _prepare_output_directory(output_dir, root_specs)
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
        write_reconciliation_diagnostic(
            resolved_output / "local_source_reconciliation_diagnostic.json",
            agreement=agreement,
            trace_primary=trace_primary,
            root_primary=root_primary,
            trace_oracle=trace_oracle,
            root_oracle=root_oracle,
            input_snapshot_identity={"mode": "live_or_manifest_roots"},
        )
        raise RuntimeError("local_source_primary_oracle_disagreement")

    trace_sha = write_json(
        resolved_output / "local_execution_trace_audit.json", trace_primary
    )
    root_sha = write_json(resolved_output / "local_root_census.json", root_primary)
    oracle_payload = {
        "schema_version": "local_unresolved_source_audit_v1",
        "trace": trace_oracle,
        "roots": root_oracle,
        "primary_oracle_agreement": agreement,
    }
    oracle_sha = write_json(
        resolved_output / "local_source_audit_oracle.json", oracle_payload
    )

    candidate_count = int(root_primary["source_candidate_count"])
    denied_candidate_count = int(
        root_primary["denied_outcome_or_pnl_candidate_count"]
    )
    if denied_candidate_count:
        decision = "LOCAL_SOURCE_CANDIDATES_FOUND_WITH_DENIED_CONTENT"
    elif candidate_count:
        decision = "LOCAL_SOURCE_CANDIDATES_FOUND_REQUIRES_HUMAN_AUTHORITY_REVIEW"
    else:
        decision = "LOCAL_SOURCE_AUDIT_COMPLETE_NO_ADDITIONAL_CANDIDATES"
    source_search_completion = (
        "INCOMPLETE_CANDIDATE_AUTHORITY_REVIEW_REQUIRED"
        if candidate_count
        else "COMPLETE_NO_ADDITIONAL_CANDIDATES"
    )

    summary = {
        "schema_version": "local_unresolved_source_audit_v1",
        "decision": decision,
        "declared_root_inventory_status": "COMPLETE",
        "source_search_completion": source_search_completion,
        "trace_candidate_id": trace_primary["candidate_id"],
        "trace_sha256": trace_primary["trace_sha256"],
        "trace_record_count": trace_primary["record_count"],
        "trace_source_disposition": trace_primary["source_disposition"],
        "declared_root_count": root_primary["declared_root_count"],
        "source_candidate_count": candidate_count,
        "denied_outcome_or_pnl_candidate_count": denied_candidate_count,
        "exact_duplicate_group_count": root_primary["exact_duplicate_group_count"],
        "remaining_uninspected_known_source_count": denied_candidate_count,
        "authority_candidate_review_required": bool(candidate_count),
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "replacement_signal_ledger_required": True,
        "primary_oracle_agreement": agreement["status"],
        "outcome_or_pnl_fields_present": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    summary_sha = write_json(
        resolved_output / "local_source_audit_summary.json", summary
    )
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
        "denied_outcome_or_pnl_candidate_count": denied_candidate_count,
        "primary_oracle_agreement": agreement["status"],
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(resolved_output / "external_evidence_manifest.json", manifest)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stream-audit the remaining execution trace and exhaust exactly the "
            "declared local source roots without candidate truncation."
        )
    )
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--root", action="append")
    parser.add_argument("--root-manifest", type=Path)
    parser.add_argument("--expected-root-count", type=int, default=27)
    parser.add_argument("--expected-trace-sha256")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root_specs = [parse_root_spec(value) for value in args.root or []]
    if args.root_manifest is not None:
        manifest_specs = load_root_manifest(args.root_manifest)
        if root_specs:
            raise ValueError("use either --root or --root-manifest, not both")
        root_specs = manifest_specs
    if not root_specs:
        raise ValueError("either --root or --root-manifest is required")
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
