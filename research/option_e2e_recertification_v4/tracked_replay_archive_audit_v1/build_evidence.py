from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .audit import EXPECTED_ARCHIVE_SHA256, audit_tracked_archive
from .oracle import oracle_archive_facts, reconcile_primary_oracle


def canonical_json(payload: Any) -> str:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        + "\n"
    )


def semantic_sha256(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def write_json(path: Path, payload: Any) -> str:
    text = canonical_json(payload)
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )
    return digest


def _compact_primary(primary: dict[str, Any]) -> dict[str, Any]:
    members = list(primary["members"])
    compact = {key: value for key, value in primary.items() if key != "members"}
    all_paths = sorted(str(item["member_path"]) for item in members)
    content_paths = sorted(
        str(item["member_path"])
        for item in members
        if not item["archive_metadata"]
    )
    metadata_paths = sorted(
        str(item["member_path"])
        for item in members
        if item["archive_metadata"]
    )
    compact.update(
        member_registry_semantic_sha256=semantic_sha256(members),
        member_path_manifest_sha256=hashlib.sha256(
            ("\n".join(all_paths) + "\n").encode("utf-8")
        ).hexdigest(),
        content_member_path_manifest_sha256=hashlib.sha256(
            ("\n".join(content_paths) + "\n").encode("utf-8")
        ).hexdigest(),
        archive_metadata_path_manifest_sha256=hashlib.sha256(
            ("\n".join(metadata_paths) + "\n").encode("utf-8")
        ).hexdigest(),
        candidate_class_counts={
            candidate_class: sum(
                item["candidate_class"] == candidate_class for item in members
            )
            for candidate_class in sorted(
                {str(item["candidate_class"]) for item in members}
            )
        },
        full_member_registry_committed=False,
        full_member_registry_location="EXTERNAL_WORKFLOW_ARTIFACT",
    )
    return compact


def build(
    archive_path: Path,
    output_dir: Path,
    *,
    expected_sha256: str = EXPECTED_ARCHIVE_SHA256,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = audit_tracked_archive(
        archive_path,
        expected_sha256=expected_sha256,
    )
    oracle = oracle_archive_facts(
        archive_path,
        expected_sha256=expected_sha256,
    )
    agreement = reconcile_primary_oracle(primary, oracle)
    if agreement["status"] != "AGREEMENT":
        raise RuntimeError("primary_oracle_disagreement")

    oracle_payload = {
        **oracle,
        "primary_oracle_agreement": agreement,
    }
    compact_primary = _compact_primary(primary)
    primary_sha = write_json(
        output_dir / "tracked_replay_archive_audit.json",
        primary,
    )
    compact_sha = write_json(
        output_dir / "tracked_replay_archive_audit_compact.json",
        compact_primary,
    )
    oracle_sha = write_json(
        output_dir / "tracked_replay_archive_audit_oracle.json",
        oracle_payload,
    )
    summary = {
        "schema_version": "tracked_replay_archive_source_audit_v1",
        "decision": "TRACKED_REPLAY_ARCHIVE_INSPECTED_NON_CANONICAL",
        "archive_sha256": primary["archive_sha256"],
        "archive_size_bytes": primary["archive_size_bytes"],
        "archive_copy_count_from_prior_census": 23,
        "unique_archive_source_count": 1,
        "member_count": primary["member_count"],
        "archive_metadata_member_count": primary["archive_metadata_member_count"],
        "content_tree_member_count": primary["content_tree_member_count"],
        "content_file_member_count": primary["content_file_member_count"],
        "content_directory_member_count": primary[
            "content_directory_member_count"
        ],
        "market_data_parquet_member_count": primary[
            "market_data_parquet_member_count"
        ],
        "option_like_parquet_member_count": primary[
            "option_like_parquet_member_count"
        ],
        "source_manifest_member_count": primary["source_manifest_member_count"],
        "represented_date_directory_count": primary[
            "represented_date_directory_count"
        ],
        "dates_with_parquet_member_count": primary[
            "dates_with_parquet_member_count"
        ],
        "denied_outcome_member_count": primary["denied_outcome_member_count"],
        "signal_like_member_count": primary["signal_like_member_count"],
        "source_disposition": primary["source_disposition"],
        "canonical_signal_source_count": 0,
        "canonical_dataset_source_count": 0,
        "primary_oracle_agreement": agreement["status"],
        "source_search_completion": "INCOMPLETE_LOCAL_ROOTS_NOT_INSPECTED",
        "remaining_known_unique_source_count": 1,
        "remaining_known_unique_source": (
            "MAIN_TRADEBOT:.runtime/logs/execution_entry_trace.jsonl"
        ),
        "remaining_declared_root_gap_count": 27,
        "replacement_signal_ledger_required": True,
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    summary_sha = write_json(
        output_dir / "tracked_replay_archive_audit_summary.json",
        summary,
    )
    manifest = {
        "schema_version": "tracked_replay_archive_source_audit_v1",
        "artifacts": {
            "tracked_replay_archive_audit.json": primary_sha,
            "tracked_replay_archive_audit_compact.json": compact_sha,
            "tracked_replay_archive_audit_oracle.json": oracle_sha,
            "tracked_replay_archive_audit_summary.json": summary_sha,
        },
        "archive_sha256": primary["archive_sha256"],
        "member_registry_semantic_sha256": compact_primary[
            "member_registry_semantic_sha256"
        ],
        "primary_oracle_agreement": agreement["status"],
        "full_member_registry_committed": False,
        "full_member_registry_location": "EXTERNAL_WORKFLOW_ARTIFACT",
        "research_only": True,
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    write_json(
        output_dir / "external_evidence_manifest.json",
        manifest,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit the frozen tracked replay archive without extraction."
    )
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--expected-sha256",
        default=EXPECTED_ARCHIVE_SHA256,
        help="Frozen archive SHA-256; defaults to the audited repository artifact.",
    )
    args = parser.parse_args()
    summary = build(
        args.archive,
        args.output_dir,
        expected_sha256=args.expected_sha256,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
