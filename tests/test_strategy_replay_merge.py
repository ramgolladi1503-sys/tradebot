from __future__ import annotations

from pathlib import Path

import pytest

from research.strategy_replay.common import StrategyReplayError, recompute_candidate_hash, selection_summary
from research.strategy_replay.merge import (
    artifact_names,
    load_artifact_bundle,
    merge_shard_payloads,
    write_artifact_bundle,
)


def _contract() -> dict[str, object]:
    return {
        "strategy_id": "trend_pullback_v1",
        "temporal_contract_version": "trend_pullback_temporal_v1",
        "production_module": "strategies.movement.trend_pullback",
        "production_callable": "strategies.movement.trend_pullback.generate_trend_pullback_candidates",
        "production_file_sha256": "f" * 64,
        "contract_hash": "c" * 64,
    }


def _record(symbol: str, session_date: str, logical_path: str, sha: str) -> dict[str, object]:
    return {
        "absolute_path": f"/tmp/{logical_path}",
        "logical_path": logical_path,
        "symbol": symbol,
        "session_date": session_date,
        "source_root": "/tmp/runtime/upstox_candidate_replay",
        "sha256": sha,
        "row_count": 375,
        "byte_size": 1024,
        "selected_via": "inventory_verified_repo_relative",
    }


def _ledger(symbol: str, session_date: str, setup_id: str) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "session_date": session_date,
            "direction": "BUY_CALL",
            "proposal_ready_at_iso": f"{session_date}T09:19:00+05:30",
            "setup_id": setup_id,
            "history_hash": f"history-{setup_id}",
        }
    ]


def _payload(*, shard_count: int, shard_index: int, record: dict[str, object], ledger: list[dict[str, object]]) -> dict[str, object]:
    execution_identity = {
        "requested_profile_id": "trend_pullback_v1",
        "resolved_profile_id": "trend_pullback_v1",
        "profile_resolution_source": "embedded_defaults",
        "runtime_profile_hash": "p" * 64,
        "dataset_manifest_hash": "d" * 64,
        "inventory_sha256": "i" * 64,
        "git_commit_sha": "g" * 40,
        "worktree_clean": True,
        "contract_hash": "c" * 64,
    }
    records = [record]
    full_source_universe = {
        "selected_record_count_before_sharding": 2,
        "semantic_hash": "u" * 64,
    }
    return {
        "contract": _contract(),
        "source_manifest": {
            "inventory_resolution": {"inventory_sha256": "i" * 64},
            "records": records,
            "full_source_universe": full_source_universe,
            "shard_metadata": {"shard_count": shard_count, "shard_index": shard_index},
        },
        "summary": {
            "shard_metadata": {"shard_count": shard_count, "shard_index": shard_index},
            "phase1_verdict": "READY",
            "candidate_semantic_hash": recompute_candidate_hash(ledger),
            "execution_identity": execution_identity,
            "full_source_universe": full_source_universe,
            "oracle_reconciliation_totals": {"checked": 1, "matched": 1, "mismatched": 0},
            "future_mutation_control_totals": {"checked": 1, "passed": 1, "failed": 0},
            "source_immutability_totals": {"checked": 1, "mismatched": 0},
        },
        "ledger": ledger,
    }


def test_merge_shards_requires_complete_clean_consistent_sets() -> None:
    record_a = _record("BANKNIFTY", "2026-07-15", "runtime/b.parquet", "b" * 64)
    record_b = _record("NIFTY", "2026-07-14", "runtime/a.parquet", "a" * 64)
    payload_a = _payload(shard_count=2, shard_index=0, record=record_a, ledger=_ledger("BANKNIFTY", "2026-07-15", "setup-b"))
    payload_b = _payload(shard_count=2, shard_index=1, record=record_b, ledger=_ledger("NIFTY", "2026-07-14", "setup-a"))
    expected_universe = {
        "selected_record_count_before_sharding": 2,
        "semantic_hash": selection_summary([record_a, record_b])["semantic_hash"],
    }
    payload_a["source_manifest"]["full_source_universe"] = expected_universe
    payload_b["source_manifest"]["full_source_universe"] = expected_universe
    payload_a["summary"]["full_source_universe"] = expected_universe
    payload_b["summary"]["full_source_universe"] = expected_universe

    merged = merge_shard_payloads(contract=_contract(), shard_payloads=[payload_a, payload_b])
    assert merged.summary["candidate_semantic_hash"] == recompute_candidate_hash(merged.ledger)
    assert merged.summary["shard_metadata"]["merged_from_shards"] is True
    assert merged.summary["phase1_verdict"] == "READY"

    duplicate = _payload(shard_count=2, shard_index=0, record=record_b, ledger=_ledger("NIFTY", "2026-07-14", "setup-a"))
    duplicate["source_manifest"]["full_source_universe"] = expected_universe
    duplicate["summary"]["full_source_universe"] = expected_universe
    with pytest.raises(StrategyReplayError, match="duplicate_shard_indexes"):
        merge_shard_payloads(contract=_contract(), shard_payloads=[payload_a, duplicate])

    dirty = _payload(shard_count=2, shard_index=1, record=record_b, ledger=_ledger("NIFTY", "2026-07-14", "setup-a"))
    dirty["source_manifest"]["full_source_universe"] = expected_universe
    dirty["summary"]["full_source_universe"] = expected_universe
    dirty["summary"]["execution_identity"]["worktree_clean"] = False
    with pytest.raises(StrategyReplayError, match="dirty_shard_cannot_merge"):
        merge_shard_payloads(contract=_contract(), shard_payloads=[payload_a, dirty])


def test_merge_shards_fails_closed_on_non_ready_or_zero_checked_controls() -> None:
    record_a = _record("BANKNIFTY", "2026-07-15", "runtime/b.parquet", "b" * 64)
    record_b = _record("NIFTY", "2026-07-14", "runtime/a.parquet", "a" * 64)
    payload_a = _payload(shard_count=2, shard_index=0, record=record_a, ledger=_ledger("BANKNIFTY", "2026-07-15", "setup-b"))
    payload_b = _payload(shard_count=2, shard_index=1, record=record_b, ledger=_ledger("NIFTY", "2026-07-14", "setup-a"))
    expected_universe = {
        "selected_record_count_before_sharding": 2,
        "semantic_hash": selection_summary([record_a, record_b])["semantic_hash"],
    }
    for payload in (payload_a, payload_b):
        payload["source_manifest"]["full_source_universe"] = expected_universe
        payload["summary"]["full_source_universe"] = expected_universe

    missing_verdict = {**payload_b, "summary": {**payload_b["summary"]}}
    missing_verdict["summary"].pop("phase1_verdict")
    with pytest.raises(StrategyReplayError, match="shard_phase1_verdict_not_ready"):
        merge_shard_payloads(contract=_contract(), shard_payloads=[payload_a, missing_verdict])

    zero_checked_a = {**payload_a, "summary": {**payload_a["summary"]}}
    zero_checked_b = {**payload_b, "summary": {**payload_b["summary"]}}
    zero_checked_a["summary"]["oracle_reconciliation_totals"] = {"checked": 0, "matched": 0, "mismatched": 0}
    zero_checked_b["summary"]["oracle_reconciliation_totals"] = {"checked": 0, "matched": 0, "mismatched": 0}
    with pytest.raises(StrategyReplayError, match="merged_replay_controls_not_ready"):
        merge_shard_payloads(contract=_contract(), shard_payloads=[zero_checked_a, zero_checked_b])


def test_write_and_load_artifact_bundle_validates_envelope_and_sidecars(tmp_path: Path) -> None:
    names = write_artifact_bundle(
        output_dir=tmp_path,
        prefix="trend_pullback_causal_replay",
        contract=_contract(),
        source_manifest={"inventory_resolution": {"inventory_sha256": "i" * 64}, "records": [], "full_source_universe": {"selected_record_count_before_sharding": 0, "semantic_hash": "0" * 64}, "shard_metadata": {"shard_count": 1, "shard_index": 0}},
        summary={"phase1_verdict": "READY", "latest_session": "2026-07-14", "execution_identity": {"git_commit_sha": "g" * 40, "worktree_clean": True}},
        ledger=[],
        candidate_id="trend_pullback_causal_replay_phase1",
    )
    bundle = load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay")
    assert bundle.contract["candidate_id"] == "trend_pullback_causal_replay_phase1"
    assert load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay").ledger == []
    assert names == artifact_names("trend_pullback_causal_replay")

    summary_path = tmp_path / names.summary
    summary_path.write_text(summary_path.read_text(encoding="utf-8").replace('"READY"', '"AUDIT_INVALID"', 1), encoding="utf-8")
    with pytest.raises(StrategyReplayError, match="artifact_sidecar_hash_mismatch"):
        load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay")


def test_load_artifact_bundle_rejects_unsafe_or_legacy_ledger_payload(tmp_path: Path) -> None:
    names = write_artifact_bundle(
        output_dir=tmp_path,
        prefix="trend_pullback_causal_replay",
        contract=_contract(),
        source_manifest={"inventory_resolution": {"inventory_sha256": "i" * 64}, "records": [], "full_source_universe": {"selected_record_count_before_sharding": 0, "semantic_hash": "0" * 64}, "shard_metadata": {"shard_count": 1, "shard_index": 0}},
        summary={"phase1_verdict": "READY", "latest_session": "2026-07-14", "execution_identity": {"git_commit_sha": "g" * 40, "worktree_clean": True}},
        ledger=[],
        candidate_id="trend_pullback_causal_replay_phase1",
    )
    ledger_path = tmp_path / names.ledger
    ledger_payload = load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay")
    assert ledger_payload.ledger == []

    legacy_ledger = []
    from research.strategy_replay.common import write_canonical_json

    write_canonical_json(ledger_path, legacy_ledger)
    with pytest.raises(StrategyReplayError, match="ledger_envelope_missing"):
        load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay")

    unsafe_payload = {
        "mode": "RESEARCH_REPLAY_ARTIFACT",
        "candidate_id": "trend_pullback_causal_replay_phase1",
        "decision": "READY",
        "reason": "ledger",
        "timestamp": "2026-07-14T15:29:00+05:30",
        "read_only": True,
        "append": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
        "source": "test",
        "entries": [],
    }
    write_canonical_json(ledger_path, unsafe_payload)
    with pytest.raises(StrategyReplayError, match="append_forbidden"):
        load_artifact_bundle(artifact_dir=tmp_path, prefix="trend_pullback_causal_replay")
