from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .audit import audit_tracked_archive
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


def write_json(path: Path, payload: Any) -> str:
    text = canonical_json(payload)
    path.write_text(text, encoding="utf-8")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    path.with_suffix(path.suffix + ".sha256").write_text(
        f"{digest}  {path.name}\n",
        encoding="utf-8",
    )
    return digest


def build(archive_path: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    primary = audit_tracked_archive(archive_path)
    oracle = oracle_archive_facts(archive_path)
    agreement = reconcile_primary_oracle(primary, oracle)
    if agreement["status"] != "AGREEMENT":
        raise RuntimeError("primary_oracle_disagreement")

    oracle_payload = {
        **oracle,
        "primary_oracle_agreement": agreement,
    }
    primary_sha = write_json(
        output_dir / "tracked_replay_archive_audit.json",
        primary,
    )
    oracle_sha = write_json(
        output_dir / "tracked_replay_archive_audit_oracle.json",
        oracle_payload,
    )
    summary = {
        "schema_version": "tracked_replay_archive_source_audit_v1",
        "decision": "TRACKED_REPLAY_ARCHIVE_INSPECTED_NON_CANONICAL",
        "archive_sha256": primary["archive_sha256"],
        "archive_copy_count_from_prior_census": 23,
        "unique_archive_source_count": 1,
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
            "tracked_replay_archive_audit_oracle.json": oracle_sha,
            "tracked_replay_archive_audit_summary.json": summary_sha,
        },
        "archive_sha256": primary["archive_sha256"],
        "primary_oracle_agreement": agreement["status"],
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
    args = parser.parse_args()
    summary = build(args.archive, args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
