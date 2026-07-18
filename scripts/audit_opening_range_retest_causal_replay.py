#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _check_sha256(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        raise SystemExit(f"missing_sidecar:{sidecar}")
    expected = sidecar.read_text(encoding="utf-8").split()[0]
    actual = hashlib.sha256(path.read_bytes().rstrip(b"\n")).hexdigest()
    if expected != actual:
        raise SystemExit(f"sha256_mismatch:{path.name}:expected={expected}:actual={actual}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit bounded opening-range-retest replay artifacts.")
    parser.add_argument("--artifact-dir", type=Path, default=Path("docs/agent_reviews"))
    args = parser.parse_args()

    summary_path = args.artifact_dir / "opening_range_retest_causal_replay_summary_v1.json"
    contract_path = args.artifact_dir / "opening_range_retest_causal_replay_contract_v1.json"
    source_manifest_path = args.artifact_dir / "opening_range_retest_causal_replay_source_manifest_v1.json"
    for path in (summary_path, contract_path, source_manifest_path):
        _check_sha256(path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    shard_metadata = dict(summary.get("shard_metadata") or {})
    shard_count = int(shard_metadata.get("shard_count") or 1)
    shard_index = shard_metadata.get("shard_index")
    merged_from_shards = bool(shard_metadata.get("merged_from_shards"))
    merged_indexes = list(shard_metadata.get("merged_shard_indexes") or [])
    if shard_count < 1:
        raise SystemExit(f"invalid_shard_count:{shard_count}")
    if merged_from_shards:
        expected = list(range(shard_count))
        if sorted(int(value) for value in merged_indexes) != expected:
            raise SystemExit(f"merged_shard_coverage_invalid:{merged_indexes}:expected={expected}")
        if shard_index is not None:
            raise SystemExit(f"merged_summary_must_not_have_shard_index:{shard_index}")
    else:
        if shard_index is None:
            raise SystemExit("non_merged_summary_missing_shard_index")
        if not 0 <= int(shard_index) < shard_count:
            raise SystemExit(f"shard_index_out_of_range:{shard_index}:{shard_count}")
    if bool(summary.get("diagnostic_mode")) and summary.get("phase1_verdict") == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY":
        raise SystemExit("diagnostic_mode_cannot_certify")
    if not bool(summary.get("authoritative_inventory_resolved")) and summary.get("phase1_verdict") == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY":
        raise SystemExit("missing_authoritative_inventory_for_certifying_verdict")
    if int(summary["oracle_mismatch_count"]) != 0:
        raise SystemExit(f"oracle_mismatch_count_nonzero:{summary['oracle_mismatch_count']}")
    if int(summary["future_mutation_control_totals"]["failed"]) != 0:
        raise SystemExit(f"future_mutation_failures_nonzero:{summary['future_mutation_control_totals']['failed']}")
    print(summary["phase1_verdict"])
    print(f"candidate_semantic_hash={summary['candidate_semantic_hash']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
