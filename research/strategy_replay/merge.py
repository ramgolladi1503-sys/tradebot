from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .common import (
    StrategyReplayError,
    canonical_json_bytes,
    load_canonical_json,
    recompute_candidate_hash,
    selection_summary,
    sorted_records,
    validate_evidence_envelope,
    validate_ledger,
    write_canonical_json,
)


@dataclass(frozen=True)
class ArtifactNames:
    contract: str
    source_manifest: str
    summary: str
    ledger: str


@dataclass(frozen=True)
class ArtifactBundle:
    contract: dict[str, Any]
    source_manifest: dict[str, Any]
    summary: dict[str, Any]
    ledger: list[dict[str, Any]]


def artifact_names(prefix: str) -> ArtifactNames:
    return ArtifactNames(
        contract=f"{prefix}_contract_v1.json",
        source_manifest=f"{prefix}_source_manifest_v1.json",
        summary=f"{prefix}_summary_v1.json",
        ledger=f"{prefix}_ledger_v1.json",
    )


def canonical_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    volatile = {"file_profiles", "elapsed_runtime_seconds", "peak_memory_bytes", "canonical_summary_semantic_hash", "shard_metadata"}
    return {key: value for key, value in summary.items() if key not in volatile}


def _evidence_reason(artifact_name: str, decision: str) -> str:
    if artifact_name.endswith("_contract_v1.json"):
        return "Replay contract artifact; summary artifact carries the certifying replay verdict."
    if artifact_name.endswith("_source_manifest_v1.json"):
        return "Replay source manifest artifact; selected sources support the published replay verdict."
    return (
        "Authoritative replay summary artifact."
        if decision != "AUDIT_INVALID"
        else "Replay summary artifact is not certifying because a fail-closed replay control rejected readiness."
    )


def _evidence_timestamp(summary: dict[str, Any]) -> str:
    proposal_ready = str(summary.get("latest_proposal_ready_timestamp") or "").strip()
    if proposal_ready:
        return proposal_ready
    session_date = str(summary.get("latest_session") or summary.get("earliest_session") or "").strip()
    if session_date:
        return f"{session_date}T15:29:00+05:30"
    return "1970-01-01T00:00:00+00:00"


def _artifact_evidence_fields(*, artifact_name: str, summary: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    decision = str(summary.get("phase1_verdict") or "AUDIT_INVALID")
    return {
        "mode": "RESEARCH_REPLAY_ARTIFACT",
        "candidate_id": candidate_id,
        "decision": decision,
        "reason": _evidence_reason(artifact_name, decision),
        "timestamp": _evidence_timestamp(summary),
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "source": f"research.strategy_replay.merge:{artifact_name}",
    }


def write_artifact_bundle(
    *,
    output_dir: Path,
    prefix: str,
    contract: dict[str, Any],
    source_manifest: dict[str, Any],
    summary: dict[str, Any],
    ledger: list[dict[str, Any]],
    candidate_id: str,
) -> ArtifactNames:
    output_dir.mkdir(parents=True, exist_ok=True)
    names = artifact_names(prefix)
    for filename, payload in (
        (names.contract, contract),
        (names.source_manifest, source_manifest),
        (names.summary, summary),
    ):
        write_canonical_json(
            output_dir / filename,
            {**_artifact_evidence_fields(artifact_name=filename, summary=summary, candidate_id=candidate_id), **payload},
        )
    write_canonical_json(
        output_dir / names.ledger,
        {
            **_artifact_evidence_fields(artifact_name=names.ledger, summary=summary, candidate_id=candidate_id),
            "entries": ledger,
        },
    )
    return names


def load_artifact_bundle(*, artifact_dir: Path, prefix: str) -> ArtifactBundle:
    names = artifact_names(prefix)
    contract = load_canonical_json(artifact_dir / names.contract)
    source_manifest = load_canonical_json(artifact_dir / names.source_manifest)
    summary = load_canonical_json(artifact_dir / names.summary)
    ledger_payload = load_canonical_json(artifact_dir / names.ledger)
    if not isinstance(ledger_payload, dict):
        raise StrategyReplayError("ledger_envelope_missing")
    for payload in (contract, source_manifest, summary, ledger_payload):
        validate_evidence_envelope(payload)
    ledger = ledger_payload.get("entries")
    if not isinstance(ledger, list):
        raise StrategyReplayError("ledger_payload_not_list")
    return ArtifactBundle(contract=contract, source_manifest=source_manifest, summary=summary, ledger=ledger)


def _validated_shard_indexes(shard_summaries: list[dict[str, Any]]) -> tuple[int, list[int]]:
    counts = {int(dict(summary.get("shard_metadata") or {}).get("shard_count") or 0) for summary in shard_summaries}
    if len(counts) != 1:
        raise StrategyReplayError(f"shard_count_mismatch:{sorted(counts)}")
    shard_count = counts.pop()
    indexes = [int(dict(summary.get("shard_metadata") or {}).get("shard_index") or 0) for summary in shard_summaries]
    if len(set(indexes)) != len(indexes):
        raise StrategyReplayError(f"duplicate_shard_indexes:{sorted(indexes)}")
    expected = list(range(shard_count))
    if sorted(indexes) != expected:
        raise StrategyReplayError(f"shard_coverage_incomplete:{sorted(indexes)}:expected={expected}")
    return shard_count, sorted(indexes)


def merge_shard_payloads(*, contract: dict[str, Any], shard_payloads: Iterable[dict[str, Any]]) -> ArtifactBundle:
    payloads = list(shard_payloads)
    if not payloads:
        raise ValueError("shard_payloads_required")
    shard_summaries = [dict(payload["summary"]) for payload in payloads]
    shard_manifests = [dict(payload["source_manifest"]) for payload in payloads]
    shard_ledgers = [list(payload["ledger"]) for payload in payloads]

    contract_hashes = {str(dict(payload["contract"]).get("contract_hash") or "") for payload in payloads}
    if len(contract_hashes) != 1 or next(iter(contract_hashes)) != str(contract.get("contract_hash") or ""):
        raise StrategyReplayError("contract_hash_mismatch")

    verdicts = [str(summary.get("phase1_verdict") or "").strip() for summary in shard_summaries]
    if any(verdict != "READY" for verdict in verdicts):
        raise StrategyReplayError(f"shard_phase1_verdict_not_ready:{verdicts}")

    shard_count, shard_indexes = _validated_shard_indexes(shard_summaries)

    execution_identities = [dict(summary.get("execution_identity") or {}) for summary in shard_summaries]
    code_shas = {str(identity.get("git_commit_sha") or "") for identity in execution_identities}
    if len(code_shas) != 1 or not next(iter(code_shas)).strip():
        raise StrategyReplayError("code_sha_mismatch_across_shards")
    if any(not bool(identity.get("worktree_clean")) for identity in execution_identities):
        raise StrategyReplayError("dirty_shard_cannot_merge")
    for key in ("requested_profile_id", "resolved_profile_id", "profile_resolution_source", "runtime_profile_hash", "contract_hash", "dataset_manifest_hash", "inventory_sha256"):
        values = {str(identity.get(key) or summary.get(key) or "") for identity, summary in zip(execution_identities, shard_summaries)}
        if len(values) != 1:
            raise StrategyReplayError(f"{key}_mismatch_across_shards")

    full_source_universes = [dict(summary.get("full_source_universe") or {}) for summary in shard_summaries]
    universe_fingerprints = {canonical_json_bytes(payload).decode("utf-8") for payload in full_source_universes}
    if len(universe_fingerprints) != 1:
        raise StrategyReplayError("source_universe_mismatch_across_shards")
    expected_source_universe = full_source_universes[0]

    combined_records = sorted_records(
        record
        for manifest in shard_manifests
        for record in list(manifest.get("records") or [])
    )
    keys = [
        (
            str(record.get("symbol") or ""),
            str(record.get("session_date") or ""),
            str(record.get("logical_path") or ""),
            str(record.get("sha256") or ""),
        )
        for record in combined_records
    ]
    if len(set(keys)) != len(keys):
        raise StrategyReplayError("duplicate_source_record_across_shards")
    if len(combined_records) != int(expected_source_universe.get("selected_record_count_before_sharding") or -1):
        raise StrategyReplayError("merged_source_universe_incomplete")
    actual_universe_hash = selection_summary(combined_records)["semantic_hash"]
    if actual_universe_hash != str(expected_source_universe.get("semantic_hash") or ""):
        raise StrategyReplayError("merged_source_universe_hash_mismatch")

    combined_ledger = [entry for ledger in shard_ledgers for entry in ledger]
    candidate_semantic_hash = validate_ledger(combined_ledger)
    for summary, ledger in zip(shard_summaries, shard_ledgers):
        validate_ledger(ledger, expected_candidate_hash=str(summary.get("candidate_semantic_hash") or ""))

    by_symbol = Counter(str(entry.get("symbol") or "") for entry in combined_ledger)
    by_direction = Counter(str(entry.get("direction") or "") for entry in combined_ledger)
    by_session = Counter(str(entry.get("session_date") or "") for entry in combined_ledger)
    combined_manifest = {
        "schema_version": 1,
        "strategy_id": contract["strategy_id"],
        "inventory_resolution": shard_manifests[0]["inventory_resolution"],
        "records": combined_records,
        "selection_summary": selection_summary(combined_records),
        "full_source_universe": dict(expected_source_universe),
        "shard_metadata": {
            "shard_count": shard_count,
            "shard_index": None,
            "is_sharded_run": True,
            "partition_rule": "sha256(canonical_session_key) mod shard_count",
            "selected_record_count_before_sharding": len(combined_records),
            "selected_record_count_after_sharding": len(combined_records),
            "merged_from_shards": True,
            "merged_shard_indexes": shard_indexes,
        },
    }
    merged_summary = {
        "schema_version": 1,
        "contract_version": contract["temporal_contract_version"],
        "production_strategy_module": contract["production_module"],
        "production_callable": contract["production_callable"],
        "production_file_sha256": contract["production_file_sha256"],
        "runtime_profile_hash": execution_identities[0]["runtime_profile_hash"],
        "dataset_manifest_hash": execution_identities[0]["dataset_manifest_hash"],
        "inventory_sha256": execution_identities[0]["inventory_sha256"],
        "selected_file_count": len(combined_records),
        "candidate_count": len(combined_ledger),
        "candidate_counts_by_symbol": dict(sorted(by_symbol.items())),
        "candidate_counts_by_direction": dict(sorted(by_direction.items())),
        "candidate_counts_by_session": dict(sorted(by_session.items())),
        "oracle_reconciliation_totals": {
            "checked": sum(int(dict(summary.get("oracle_reconciliation_totals") or {}).get("checked") or 0) for summary in shard_summaries),
            "matched": sum(int(dict(summary.get("oracle_reconciliation_totals") or {}).get("matched") or 0) for summary in shard_summaries),
            "mismatched": sum(int(dict(summary.get("oracle_reconciliation_totals") or {}).get("mismatched") or 0) for summary in shard_summaries),
        },
        "future_mutation_control_totals": {
            "checked": sum(int(dict(summary.get("future_mutation_control_totals") or {}).get("checked") or 0) for summary in shard_summaries),
            "passed": sum(int(dict(summary.get("future_mutation_control_totals") or {}).get("passed") or 0) for summary in shard_summaries),
            "failed": sum(int(dict(summary.get("future_mutation_control_totals") or {}).get("failed") or 0) for summary in shard_summaries),
        },
        "source_immutability_totals": {
            "checked": sum(int(dict(summary.get("source_immutability_totals") or {}).get("checked") or 0) for summary in shard_summaries),
            "mismatched": sum(int(dict(summary.get("source_immutability_totals") or {}).get("mismatched") or 0) for summary in shard_summaries),
            "status": "not_mutated",
        },
        "phase1_verdict": "READY",
        "candidate_semantic_hash": candidate_semantic_hash,
        "execution_identity": execution_identities[0],
        "full_source_universe": dict(expected_source_universe),
        "shard_metadata": {
            "shard_count": shard_count,
            "shard_index": None,
            "is_sharded_run": True,
            "partition_rule": "sha256(canonical_session_key) mod shard_count",
            "merged_from_shards": True,
            "selected_file_count_before_sharding": len(combined_records),
            "selected_file_count_after_sharding": len(combined_records),
            "merged_shard_indexes": shard_indexes,
        },
    }
    if (
        int(merged_summary["oracle_reconciliation_totals"]["mismatched"]) != 0
        or int(merged_summary["future_mutation_control_totals"]["failed"]) != 0
        or int(merged_summary["source_immutability_totals"]["mismatched"]) != 0
    ):
        merged_summary["phase1_verdict"] = "AUDIT_INVALID"
    if (
        int(merged_summary["oracle_reconciliation_totals"]["checked"]) <= 0
        or int(merged_summary["future_mutation_control_totals"]["checked"]) <= 0
        or int(merged_summary["source_immutability_totals"]["checked"]) <= 0
    ):
        merged_summary["phase1_verdict"] = "AUDIT_INVALID"
    merged_summary["canonical_summary_semantic_hash"] = recompute_candidate_hash([canonical_summary_payload(merged_summary)])
    if merged_summary["phase1_verdict"] != "READY":
        raise StrategyReplayError(f"merged_replay_controls_not_ready:{merged_summary['phase1_verdict']}")
    return ArtifactBundle(contract=contract, source_manifest=combined_manifest, summary=merged_summary, ledger=combined_ledger)
