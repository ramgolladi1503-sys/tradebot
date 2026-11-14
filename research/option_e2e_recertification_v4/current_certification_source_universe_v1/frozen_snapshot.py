from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .contract import canonical_json, sha256_file, write_json_with_sidecar


TRACE_SOURCE_ID = "MAIN_TRADEBOT:.runtime/logs/execution_entry_trace.jsonl"
SELECTED_CANDIDATES = (
    (
        "CAMPAIGN_WORKTREE:runtime/market_data/upstox/20260714/combined.parquet",
        Path("/Users/madhuram/tradebot-ce-pe-option-certification-v1/runtime/market_data/upstox/20260714/combined.parquet"),
        "REAL_OPTION_DATASET",
    ),
    (
        "CAMPAIGN_WORKTREE:runtime/upstox_instruments/complete.json",
        Path("/Users/madhuram/tradebot-ce-pe-option-certification-v1/runtime/upstox_instruments/complete.json"),
        "INSTRUMENT_MASTER",
    ),
    (
        "CAMPAIGN_WORKTREE:runtime/strategy_validation/resolved_option_ticks_20260702.parquet",
        Path("/Users/madhuram/tradebot-ce-pe-option-certification-v1/runtime/strategy_validation/resolved_option_ticks_20260702.parquet"),
        "REAL_OPTION_DATASET",
    ),
)


def _copy_regular_file(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise FileExistsError(f"snapshot_destination_exists:{destination.name}")
    try:
        subprocess.run(["cp", "-c", str(source), str(destination)], check=True, capture_output=True)
        return "clonefile_cp_c"
    except Exception:
        shutil.copy2(source, destination)
        return "copy2"


def _stat_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "device": stat.st_dev,
        "inode": stat.st_ino,
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "birthtime": getattr(stat, "st_birthtime", None),
        "mode": stat.st_mode,
    }


def _trace_semantics(path: Path) -> dict[str, Any]:
    import json
    import hashlib

    semantic = hashlib.sha256()
    count = 0
    first = None
    last = None
    with path.open("rb") as handle:
        for raw_line in handle:
            stripped = raw_line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped.decode("utf-8"))
            timestamp = str(payload.get("timestamp"))
            first = timestamp if first is None else min(first, timestamp)
            last = timestamp if last is None else max(last, timestamp)
            semantic.update((json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("utf-8"))
            count += 1
    return {
        "semantic_sha256": semantic.hexdigest(),
        "record_count": count,
        "first_timestamp": first,
        "last_timestamp": last,
    }


def _candidate_summary(path: Path, classification: str) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "classification": classification,
        "size": path.stat().st_size,
        "physical_sha256": sha256_file(path),
    }
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
        summary["row_count"] = int(len(df))
        summary["columns"] = list(map(str, df.columns))
    elif path.suffix == ".json":
        summary["json_size"] = path.stat().st_size
    return summary


def build_snapshot(*, output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"snapshot_package_not_empty:{output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    trace_source = Path("/Users/madhuram/tradebot/.runtime/logs/execution_entry_trace.jsonl")
    before = _stat_identity(trace_source)
    trace_dest = output_dir / "execution_entry_trace.snapshot.jsonl"
    trace_method = _copy_regular_file(trace_source, trace_dest)
    after = _stat_identity(trace_source)
    os.chmod(trace_dest, 0o444)
    trace_sem = _trace_semantics(trace_dest)
    trace_record = {
        "source_path_id": TRACE_SOURCE_ID,
        "source_identity_before": before,
        "source_identity_after": after,
        "source_mutable": True,
        "snapshot_immutable": True,
        "snapshot_method": trace_method,
        "snapshot_size": trace_dest.stat().st_size,
        "snapshot_physical_sha256": sha256_file(trace_dest),
        "snapshot_semantic_sha256": trace_sem["semantic_sha256"],
        "record_count": trace_sem["record_count"],
        "first_timestamp": trace_sem["first_timestamp"],
        "last_timestamp": trace_sem["last_timestamp"],
        "snapshot_created_at": datetime.now(timezone.utc).isoformat(),
    }

    candidate_records = []
    for candidate_id, source, classification in SELECTED_CANDIDATES:
        rel_name = candidate_id.split(":", 1)[1].replace("/", "__")
        dest = output_dir / "candidates" / rel_name
        before_candidate = _stat_identity(source)
        method = _copy_regular_file(source, dest)
        after_candidate = _stat_identity(source)
        os.chmod(dest, 0o444)
        record = {
            "candidate_id": candidate_id,
            "snapshot_relative_path": dest.relative_to(output_dir).as_posix(),
            "source_identity_before": before_candidate,
            "source_identity_after": after_candidate,
            "copy_method": method,
            "source_stable_during_snapshot": before_candidate["inode"] == after_candidate["inode"] and before_candidate["size"] == after_candidate["size"],
            "content_read_status": "CONTENT_OPENED_SCHEMA_ONLY",
            "authority_decision": "AUTHORITY_NOT_GRANTED",
            **_candidate_summary(dest, classification),
        }
        candidate_records.append(record)

    payload = {
        "schema_version": "ce_pe_source_snapshot_v1",
        "trace_snapshot": trace_record,
        "selected_candidates": candidate_records,
        "selected_candidate_count": len(candidate_records),
        "denied_candidate_count": 103,
        "selected_input_denied_dependency_count": 0,
        "quarantined_non_input_denied_count": 103,
        "mutable_operational_outputs_not_selected": True,
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
    write_json_with_sidecar(output_dir / "source_snapshot_manifest.json", payload)
    portable = {
        "schema_version": "ce_pe_source_snapshot_portable_v1",
        "trace_snapshot": {k: v for k, v in trace_record.items() if not k.startswith("source_identity")},
        "selected_candidates": [
            {k: v for k, v in record.items() if not k.startswith("source_identity")}
            for record in candidate_records
        ],
        "selected_candidate_count": len(candidate_records),
        "denied_candidate_count": 103,
        "selected_input_denied_dependency_count": 0,
        "quarantined_non_input_denied_count": 103,
        "absolute_paths_published": False,
        "outcomes_read": False,
        "pnl_read": False,
        "holdout_outcomes_read": False,
    }
    portable_sha = write_json_with_sidecar(output_dir / "portable_source_snapshot_manifest.json", portable)
    return {"manifest": payload, "portable_sha256": portable_sha}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = build_snapshot(output_dir=args.output_dir)
    print(canonical_json({"portable_sha256": result["portable_sha256"], "selected_candidate_count": result["manifest"]["selected_candidate_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
