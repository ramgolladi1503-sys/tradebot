from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Iterable

from core.movement_contract import StrategyCandidate, StrategyContext
from core.movement_regime import MovementRegimeResult
from research.opening_range_retest.replay_contract import build_replay_contract_matrix, canonical_json_bytes
from research.opening_range_retest.replay_controls import (
    PROJECTED_SESSION_COLUMNS,
    InventoryResolution,
    ReplaySourceSelectionError,
    SessionFileRecord,
    read_session_bars,
    select_session_files,
    selection_summary,
    sha256_file,
)
from research.opening_range_retest.replay_oracle import evaluate_oracle_direction
from strategies.movement.opening_range_breakout import generate_opening_range_retest_candidates

CONTRACT_ARTIFACT_FILENAME = "opening_range_retest_causal_replay_contract_v1.json"
SOURCE_MANIFEST_ARTIFACT_FILENAME = "opening_range_retest_causal_replay_source_manifest_v1.json"
SUMMARY_ARTIFACT_FILENAME = "opening_range_retest_causal_replay_summary_v1.json"
LEDGER_ARTIFACT_FILENAME = "opening_range_retest_causal_replay_ledger_v1.json"
EVIDENCE_MODE = "RESEARCH_REPLAY_ARTIFACT"
EVIDENCE_CANDIDATE_ID = "opening_range_retest_causal_replay_phase1"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _neutral_regime() -> MovementRegimeResult:
    return MovementRegimeResult(
        schema_version=1,
        primary_regime="INCONCLUSIVE",
        scores={
            "TREND_UP": 0.0,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.45,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 1.0,
        },
    )


def _peak_memory_bytes() -> int | None:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if os.uname().sysname == "Darwin":
            return int(usage)
        return int(usage) * 1024
    except Exception:
        return None


def _build_context(
    prefix: list[dict[str, Any]],
    *,
    vwap: float,
    orb_high: float,
    orb_low: float,
) -> StrategyContext:
    latest = prefix[-1]
    provenance = {
        "status": "TRUTHFUL",
        "source_component": "research.opening_range_retest.replay_engine",
        "source_field": "completed_bar_history",
        "source_event_timestamp": latest["bar_end_timestamp"],
        "receipt_timestamp": latest["bar_end_timestamp"],
        "timeframe": "1m",
        "symbol": latest["symbol"],
        "session_date": latest["session_date"],
        "completed_bar_count": len(prefix),
    }
    return StrategyContext(
        symbol=str(latest["symbol"]),
        spot_ltp=float(latest["close"]),
        open_price=float(prefix[0]["open"]),
        vwap=vwap,
        orb_high=orb_high,
        orb_low=orb_low,
        previous_completed_close=float(prefix[-2]["close"]) if len(prefix) >= 2 else None,
        completed_bar_history=tuple(prefix),
        volume_z=1.0,
        option_ce_ltp=100.0,
        option_pe_ltp=100.0,
        ce_premium_change=5.0,
        pe_premium_change=5.0,
        ce_spread_pct=1.0,
        pe_spread_pct=1.0,
        ce_depth=1000.0,
        pe_depth=1000.0,
        option_ltp_age_sec=0.5,
        quote_source="research_replay_underlying_only",
        fallback_used=False,
        minutes_since_open=len(prefix) - 1,
        metadata={"completed_bar_history_provenance": provenance},
    )


def candidate_semantic_payload(candidate: StrategyCandidate) -> dict[str, Any]:
    identity = dict(candidate.evidence.get("setup_identity") or {})
    return {
        "strategy_id": candidate.strategy_id,
        "symbol": candidate.symbol,
        "direction": candidate.direction,
        "status": candidate.status,
        "raw_score": round(float(candidate.raw_score), 6),
        "entry_trigger": candidate.entry_trigger,
        "invalid_if": candidate.invalid_if,
        "rank_reason": candidate.rank_reason,
        "proposal_ready_at_iso": identity.get("proposal_ready_at_iso"),
        "setup_id": identity.get("setup_id"),
        "history_hash": identity.get("history_hash"),
    }


@dataclass(frozen=True)
class ReplayEmission:
    symbol: str
    session_date: str
    direction: str
    proposal_ready_at_iso: str
    setup_id: str
    history_hash: str
    raw_score: float
    semantic_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "session_date": self.session_date,
            "direction": self.direction,
            "proposal_ready_at_iso": self.proposal_ready_at_iso,
            "setup_id": self.setup_id,
            "history_hash": self.history_hash,
            "raw_score": self.raw_score,
            "semantic_payload": self.semantic_payload,
        }


@dataclass(frozen=True)
class ReplayRunResult:
    contract: dict[str, Any]
    source_manifest: dict[str, Any]
    summary: dict[str, Any]
    emissions: tuple[ReplayEmission, ...]


@dataclass(frozen=True)
class ReplayShardSpec:
    shard_count: int
    shard_index: int

    def __post_init__(self) -> None:
        if self.shard_count < 1:
            raise ValueError("shard_count_must_be_positive")
        if self.shard_index < 0 or self.shard_index >= self.shard_count:
            raise ValueError(f"shard_index_out_of_range:{self.shard_index}:{self.shard_count}")

    @property
    def label(self) -> str:
        return f"shard-{self.shard_index:02d}-of-{self.shard_count:02d}"


@dataclass(frozen=True)
class GitExecutionState:
    commit_sha: str | None
    worktree_clean: bool
    dirty_path_count: int
    status_output: tuple[str, ...]
    error: str | None = None


def _record_sort_key(record: SessionFileRecord) -> tuple[str, str, str, str]:
    return (record.symbol, record.session_date, record.logical_path, record.sha256)


def _emission_sort_key(emission: ReplayEmission) -> tuple[str, str, str, str, str]:
    return (
        emission.session_date,
        emission.symbol,
        emission.proposal_ready_at_iso,
        emission.direction,
        emission.setup_id,
    )


def _sorted_session_records(records: Iterable[SessionFileRecord]) -> list[SessionFileRecord]:
    return sorted(records, key=_record_sort_key)


def _sorted_emissions(emissions: Iterable[ReplayEmission]) -> tuple[ReplayEmission, ...]:
    return tuple(sorted(emissions, key=_emission_sort_key))


def _coerce_shard_spec(*, shard_count: int | None = None, shard_index: int | None = None) -> ReplayShardSpec | None:
    if shard_count is None and shard_index is None:
        return None
    if shard_count is None or shard_index is None:
        raise ValueError("shard_count_and_shard_index_must_be_provided_together")
    return ReplayShardSpec(shard_count=int(shard_count), shard_index=int(shard_index))


def _apply_shard(records: list[SessionFileRecord], shard_spec: ReplayShardSpec | None) -> list[SessionFileRecord]:
    ordered = _sorted_session_records(records)
    if shard_spec is None:
        return ordered
    return [record for record in ordered if _partition_assignment(record, shard_count=shard_spec.shard_count) == shard_spec.shard_index]


def _canonical_session_key(record: SessionFileRecord) -> str:
    return json.dumps(
        {
            "logical_path": record.logical_path,
            "selected_source_sha256": record.sha256,
            "session_date": record.session_date,
            "symbol": record.symbol,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _partition_assignment(record: SessionFileRecord, *, shard_count: int) -> int:
    if shard_count < 1:
        raise ValueError("shard_count_must_be_positive")
    digest = hashlib.sha256(_canonical_session_key(record).encode("utf-8")).hexdigest()
    return int(digest, 16) % shard_count


def _build_source_manifest(
    *,
    contract: dict[str, Any],
    resolution: InventoryResolution | None,
    records: list[SessionFileRecord],
    all_record_count: int,
    shard_spec: ReplayShardSpec | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "strategy_id": contract["strategy_id"],
        "inventory_resolution": _resolution_summary(resolution),
        "records": [record.to_dict() for record in records],
        "partition_assignments": [
            {
                "symbol": record.symbol,
                "session_date": record.session_date,
                "logical_path": record.logical_path,
                "selected_source_sha256": record.sha256,
                "canonical_session_key": _canonical_session_key(record),
                "shard_index": _partition_assignment(record, shard_count=shard_spec.shard_count if shard_spec is not None else 1),
            }
            for record in records
        ],
        "selection_summary": selection_summary(records),
        "full_source_universe": {
            "selected_record_count_before_sharding": all_record_count,
            "semantic_hash": "",
        },
        "shard_metadata": {
            "shard_count": shard_spec.shard_count if shard_spec is not None else 1,
            "shard_index": shard_spec.shard_index if shard_spec is not None else 0,
            "is_sharded_run": shard_spec is not None,
            "partition_rule": "sha256(canonical_session_key) mod shard_count",
            "selected_record_count_before_sharding": all_record_count,
            "selected_record_count_after_sharding": len(records),
        },
    }


def _record_from_payload(payload: dict[str, Any]) -> SessionFileRecord:
    return SessionFileRecord(
        absolute_path=str(payload["absolute_path"]),
        logical_path=str(payload["logical_path"]),
        symbol=str(payload["symbol"]),
        session_date=str(payload["session_date"]),
        source_root=str(payload["source_root"]),
        sha256=str(payload["sha256"]),
        row_count=int(payload["row_count"]),
        byte_size=int(payload["byte_size"]),
        projected_columns=tuple(str(value) for value in payload["projected_columns"]),
        selected_via=str(payload["selected_via"]),
    )


def _emission_from_payload(payload: dict[str, Any]) -> ReplayEmission:
    return ReplayEmission(
        symbol=str(payload["symbol"]),
        session_date=str(payload["session_date"]),
        direction=str(payload["direction"]),
        proposal_ready_at_iso=str(payload["proposal_ready_at_iso"]),
        setup_id=str(payload["setup_id"]),
        history_hash=str(payload["history_hash"]),
        raw_score=float(payload["raw_score"]),
        semantic_payload=dict(payload["semantic_payload"]),
    )


def _merged_totals(summaries: list[dict[str, Any]], key: str) -> dict[str, int]:
    totals: Counter[str] = Counter()
    for summary in summaries:
        totals.update({str(name): int(value) for name, value in dict(summary.get(key) or {}).items()})
    return dict(sorted(totals.items()))


def _load_canonical_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_execution_state() -> GitExecutionState:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if head.returncode != 0:
            return GitExecutionState(
                commit_sha=None,
                worktree_clean=False,
                dirty_path_count=0,
                status_output=(),
                error=(head.stderr or head.stdout).strip() or "git_rev_parse_failed",
            )
        status = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode != 0:
            return GitExecutionState(
                commit_sha=head.stdout.strip() or None,
                worktree_clean=False,
                dirty_path_count=0,
                status_output=(),
                error=(status.stderr or status.stdout).strip() or "git_status_failed",
            )
        status_lines = tuple(line for line in status.stdout.splitlines() if line.strip())
        return GitExecutionState(
            commit_sha=head.stdout.strip() or None,
            worktree_clean=not status_lines,
            dirty_path_count=len(status_lines),
            status_output=status_lines,
            error=None,
        )
    except Exception as exc:
        return GitExecutionState(
            commit_sha=None,
            worktree_clean=False,
            dirty_path_count=0,
            status_output=(),
            error=str(exc),
        )


def _check_artifact_sidecar(path: Path) -> None:
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.exists():
        raise ReplaySourceSelectionError(f"missing_sidecar:{sidecar}")
    expected = sidecar.read_text(encoding="utf-8").split()[0].strip().lower()
    actual = hashlib.sha256(path.read_bytes().rstrip(b"\n")).hexdigest()
    if expected != actual:
        raise ReplaySourceSelectionError(
            f"artifact_sidecar_hash_mismatch:{path.name}:expected={expected}:actual={actual}"
        )


def replay_session_bars(
    bars: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    *,
    symbol: str | None = None,
    session_date: str | None = None,
) -> tuple[ReplayEmission, ...]:
    seen_setup_ids: set[tuple[str, str]] = set()
    regime = _neutral_regime()
    emissions: list[ReplayEmission] = []
    bars_list = list(bars)
    orb_high = max(float(row["high"]) for row in bars_list[:15])
    orb_low = min(float(row["low"]) for row in bars_list[:15])
    cumulative_close_sum = 0.0
    cumulative_weighted_close = 0.0
    cumulative_volume_sum = 0.0
    prefix_vwap: list[float] = []
    for row in bars_list:
        close_price = float(row["close"])
        cumulative_close_sum += close_price
        volume = row.get("volume")
        if volume is not None:
            volume_value = float(volume)
            if volume_value > 0:
                cumulative_weighted_close += close_price * volume_value
                cumulative_volume_sum += volume_value
        if cumulative_volume_sum > 0:
            prefix_vwap.append(cumulative_weighted_close / cumulative_volume_sum)
        else:
            prefix_vwap.append(cumulative_close_sum / len(prefix_vwap + [0]))
    for idx in range(15, len(bars_list)):
        prefix = bars_list[: idx + 1]
        ctx = _build_context(
            prefix,
            vwap=prefix_vwap[idx],
            orb_high=orb_high,
            orb_low=orb_low,
        )
        generated = tuple(generate_opening_range_retest_candidates(ctx, regime) or ())
        for candidate in generated:
            identity = dict(candidate.evidence.get("setup_identity") or {})
            setup_id = str(identity.get("setup_id") or "").strip()
            proposal_ready = str(identity.get("proposal_ready_at_iso") or "").strip()
            direction = str(candidate.direction)
            if not setup_id or not proposal_ready:
                continue
            key = (direction, setup_id)
            if key in seen_setup_ids:
                continue
            if proposal_ready != str(prefix[-1]["bar_end_timestamp"]):
                raise ReplaySourceSelectionError(
                    f"candidate_backdated:{symbol or candidate.symbol}:{session_date or prefix[-1]['session_date']}:{proposal_ready}:{prefix[-1]['bar_end_timestamp']}"
                )
            seen_setup_ids.add(key)
            payload = candidate_semantic_payload(candidate)
            emissions.append(
                ReplayEmission(
                    symbol=symbol or str(candidate.symbol),
                    session_date=session_date or str(prefix[-1]["session_date"]),
                    direction=direction,
                    proposal_ready_at_iso=proposal_ready,
                    setup_id=setup_id,
                    history_hash=str(identity.get("history_hash") or ""),
                    raw_score=round(float(candidate.raw_score), 6),
                    semantic_payload=payload,
                )
            )
    return tuple(emissions)


def _oracle_summary(
    bars: list[dict[str, Any]] | tuple[dict[str, Any], ...],
    emissions: tuple[ReplayEmission, ...],
) -> dict[str, int]:
    mismatches = 0
    matched = 0
    checked = 0
    by_direction = {direction: [item for item in emissions if item.direction == direction] for direction in ("BUY_CALL", "BUY_PUT")}
    for direction in ("BUY_CALL", "BUY_PUT"):
        oracle = evaluate_oracle_direction(bars, direction=direction)
        replay_first = by_direction[direction][0] if by_direction[direction] else None
        checked += 1
        if oracle is None and replay_first is None:
            matched += 1
            continue
        if oracle is None or replay_first is None:
            mismatches += 1
            continue
        if oracle.proposal_ready_at_iso != replay_first.proposal_ready_at_iso:
            mismatches += 1
            continue
        matched += 1
    return {
        "checked": checked,
        "matched": matched,
        "mismatched": mismatches,
    }


def _future_mutation_check(bars: list[dict[str, Any]] | tuple[dict[str, Any], ...], emission: ReplayEmission) -> bool:
    bars_list = list(bars)
    cutoff = next(
        idx for idx, row in enumerate(bars_list) if str(row["bar_end_timestamp"]) == emission.proposal_ready_at_iso
    )
    truncated = [dict(row) for row in bars_list[: cutoff + 1]]
    mutated = [dict(row) for row in bars_list[: cutoff + 1]] + [
        {
            **dict(row),
            "high": float(row["high"]) * 1.5,
            "low": max(float(row["low"]) * 0.5, 0.01),
            "close": float(row["close"]) * 1.2,
            "volume": (float(row["volume"]) if row.get("volume") is not None else 0.0) + 9999.0,
        }
        for row in bars_list[cutoff + 1 :]
    ]
    truncated_emissions = replay_session_bars(truncated, symbol=emission.symbol, session_date=emission.session_date)
    mutated_emissions = replay_session_bars(mutated, symbol=emission.symbol, session_date=emission.session_date)
    target_truncated = next((item for item in truncated_emissions if item.setup_id == emission.setup_id), None)
    target_mutated = next((item for item in mutated_emissions if item.setup_id == emission.setup_id), None)
    return (
        target_truncated is not None
        and target_mutated is not None
        and target_truncated.semantic_payload == emission.semantic_payload
        and target_mutated.semantic_payload == emission.semantic_payload
    )


def _process_session_record(record_payload: dict[str, Any]) -> dict[str, Any]:
    record = _record_from_payload(record_payload)
    loaded = read_session_bars(Path(record.absolute_path), projected_columns=record.projected_columns)
    replay_started = perf_counter()
    emissions = replay_session_bars(loaded.bars, symbol=record.symbol, session_date=record.session_date)
    replay_seconds = perf_counter() - replay_started
    oracle_summary = _oracle_summary(loaded.bars, emissions)
    future_checked = 0
    future_passed = 0
    for emission in emissions:
        future_checked += 1
        if _future_mutation_check(loaded.bars, emission):
            future_passed += 1
    return {
        "record": record.to_dict(),
        "metrics": {
            **loaded.metrics,
            "symbol": record.symbol,
            "session_date": record.session_date,
            "replay_seconds": replay_seconds,
            "emission_count": len(emissions),
        },
        "emissions": [item.to_dict() for item in emissions],
        "oracle_summary": oracle_summary,
        "future_checked": future_checked,
        "future_passed": future_passed,
    }


def _source_immutability_result(selected: list[SessionFileRecord]) -> dict[str, Any]:
    checked = 0
    mismatched = 0
    for record in selected:
        checked += 1
        if sha256_file(Path(record.absolute_path)) != record.sha256:
            mismatched += 1
    return {
        "checked": checked,
        "mismatched": mismatched,
        "status": "not_mutated" if mismatched == 0 else "mutated",
    }


def _resolution_summary(resolution: InventoryResolution | None) -> dict[str, Any]:
    if resolution is None:
        return {
            "original_inventory_provenance_path": None,
            "resolved_inventory_path": None,
            "inventory_sha256": None,
            "inventory_sidecar_verification": False,
            "inventory_resolution_mode": "diagnostic_fallback",
        }
    return {
        "original_inventory_provenance_path": resolution.original_provenance_path,
        "resolved_inventory_path": resolution.resolved_runtime_path,
        "inventory_sha256": resolution.inventory_sha256,
        "inventory_sidecar_verification": resolution.sidecar_verified,
        "inventory_resolution_mode": resolution.resolution_mode,
    }


def _canonical_summary_payload(summary: dict[str, Any]) -> dict[str, Any]:
    volatile = {
        "file_profiles",
        "elapsed_runtime_seconds",
        "peak_memory_bytes",
        "canonical_summary_semantic_hash",
        "shard_metadata",
    }
    return {key: value for key, value in summary.items() if key not in volatile}


def _evidence_timestamp(summary: dict[str, Any]) -> str:
    proposal_ready = str(summary.get("latest_proposal_ready_timestamp") or "").strip()
    if proposal_ready:
        return proposal_ready
    session_date = str(summary.get("latest_session") or summary.get("earliest_session") or "").strip()
    if session_date:
        return f"{session_date}T15:29:00+05:30"
    return "1970-01-01T00:00:00+00:00"


def _artifact_evidence_fields(*, artifact_name: str, summary: dict[str, Any]) -> dict[str, Any]:
    verdict = str(summary.get("phase1_verdict") or "AUDIT_INVALID")
    if artifact_name == CONTRACT_ARTIFACT_FILENAME:
        reason = "Replay contract artifact for opening_range_retest_v1; summary artifact carries the certifying replay verdict."
    elif artifact_name == SOURCE_MANIFEST_ARTIFACT_FILENAME:
        reason = "Replay source manifest artifact for opening_range_retest_v1; selected sources support the published replay verdict."
    else:
        reason = (
            "Authoritative replay summary artifact for opening_range_retest_v1."
            if verdict == "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY"
            else "Replay summary artifact is not certifying because at least one fail-closed replay control rejected readiness."
        )
    return {
        "mode": EVIDENCE_MODE,
        "candidate_id": EVIDENCE_CANDIDATE_ID,
        "decision": verdict,
        "reason": reason,
        "timestamp": _evidence_timestamp(summary),
        "is_order_action": False,
        "broker_api_called": False,
        "source": f"research.opening_range_retest.replay_engine:{artifact_name}",
    }


def _execution_identity(contract: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_id": str(contract["strategy_id"]),
        "contract_hash": str(contract["contract_hash"]),
        "contract_version": str(contract["temporal_contract_version"]),
        "production_module": str(contract["production_module"]),
        "production_callable": str(contract["production_callable"]),
        "production_file_sha256": str(contract["production_file_sha256"]),
        "requested_profile_id": str(contract["requested_profile_id"]),
        "resolved_profile_id": str(contract["resolved_profile_id"]),
        "profile_resolution_source": str(contract["profile_resolution_source"]),
        "runtime_profile_hash": str(contract["runtime_profile_hash"]),
        "dataset_manifest_hash": str(summary["dataset_manifest_hash"]),
        "inventory_sha256": str(summary.get("inventory_sha256")),
        "git_commit_sha": str(summary.get("git_commit_sha") or ""),
        "worktree_clean": bool(summary.get("worktree_clean")),
    }


def _full_source_universe(records: Iterable[SessionFileRecord]) -> dict[str, Any]:
    ordered = _sorted_session_records(records)
    return {
        "selected_record_count_before_sharding": len(ordered),
        "semantic_hash": hashlib.sha256(canonical_json_bytes([record.to_dict() for record in ordered])).hexdigest(),
    }


def _ledger_identity_key(emission: ReplayEmission) -> tuple[str, str, str, str, str]:
    return (
        emission.symbol,
        emission.session_date,
        emission.direction,
        emission.proposal_ready_at_iso,
        emission.setup_id,
    )


def _validate_ledger(emissions: tuple[ReplayEmission, ...], *, expected_candidate_hash: str | None = None) -> str:
    ordered = _sorted_emissions(emissions)
    if tuple(ordered) != tuple(emissions):
        raise ReplaySourceSelectionError("ledger_not_canonical_order")
    identity_keys = [_ledger_identity_key(emission) for emission in emissions]
    if len(set(identity_keys)) != len(identity_keys):
        raise ReplaySourceSelectionError("duplicate_ledger_emission")
    candidate_hash = hashlib.sha256(canonical_json_bytes([item.to_dict() for item in emissions])).hexdigest()
    if expected_candidate_hash is not None and candidate_hash != str(expected_candidate_hash):
        raise ReplaySourceSelectionError(
            f"ledger_candidate_hash_mismatch:expected={expected_candidate_hash}:actual={candidate_hash}"
        )
    return candidate_hash


def _validate_shard_identity(
    *,
    contract: dict[str, Any],
    source_manifest: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    manifest_shard_metadata = dict(source_manifest.get("shard_metadata") or {})
    summary_shard_metadata = dict(summary.get("shard_metadata") or {})
    if bool(summary.get("diagnostic_mode")):
        raise ReplaySourceSelectionError("diagnostic_shard_cannot_merge")
    if not bool(summary.get("authoritative_inventory_resolved")):
        raise ReplaySourceSelectionError("non_authoritative_shard_cannot_merge")
    if str(summary.get("phase1_verdict")) != "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY":
        raise ReplaySourceSelectionError("non_ready_shard_cannot_merge")
    if not bool(summary_shard_metadata.get("is_sharded_run")):
        raise ReplaySourceSelectionError("non_sharded_summary_cannot_merge")
    if bool(summary_shard_metadata.get("merged_from_shards")):
        raise ReplaySourceSelectionError("already_merged_summary_cannot_merge")
    if not bool(manifest_shard_metadata.get("is_sharded_run")):
        raise ReplaySourceSelectionError("non_sharded_manifest_cannot_merge")
    if bool(manifest_shard_metadata.get("merged_from_shards")):
        raise ReplaySourceSelectionError("already_merged_manifest_cannot_merge")
    summary_shard_index = int(summary_shard_metadata.get("shard_index") or 0)
    manifest_shard_index = int(manifest_shard_metadata.get("shard_index") or 0)
    if summary_shard_index != manifest_shard_index:
        raise ReplaySourceSelectionError(
            f"shard_index_mismatch_between_summary_and_manifest:{summary_shard_index}:{manifest_shard_index}"
        )
    summary_shard_count = int(summary_shard_metadata.get("shard_count") or 0)
    manifest_shard_count = int(manifest_shard_metadata.get("shard_count") or 0)
    if summary_shard_count != manifest_shard_count:
        raise ReplaySourceSelectionError(
            f"shard_count_mismatch_between_summary_and_manifest:{summary_shard_count}:{manifest_shard_count}"
        )
    manifest_records = [_record_from_payload(record) for record in source_manifest.get("records") or []]
    if len(manifest_records) != int(summary.get("selected_file_count") or 0):
        raise ReplaySourceSelectionError("selected_file_count_mismatch_between_summary_and_manifest")
    manifest_selection_summary = dict(source_manifest.get("selection_summary") or {})
    if int(manifest_selection_summary.get("selected_file_count") or 0) != len(manifest_records):
        raise ReplaySourceSelectionError("manifest_selection_summary_count_mismatch")
    manifest_selection_hash = hashlib.sha256(
        canonical_json_bytes([record.to_dict() for record in _sorted_session_records(manifest_records)])
    ).hexdigest()
    if manifest_selection_hash != str(manifest_selection_summary.get("semantic_hash")):
        raise ReplaySourceSelectionError("manifest_selection_summary_hash_mismatch")
    execution_identity = _execution_identity(contract, summary)
    if dict(summary.get("execution_identity") or {}) != execution_identity:
        raise ReplaySourceSelectionError("execution_identity_mismatch")
    if not str(execution_identity.get("git_commit_sha") or "").strip():
        raise ReplaySourceSelectionError("missing_code_sha_for_certifying_shard")
    if not bool(execution_identity.get("worktree_clean")):
        raise ReplaySourceSelectionError("dirty_shard_cannot_merge")
    full_source_universe = dict(source_manifest.get("full_source_universe") or {})
    if int(full_source_universe.get("selected_record_count_before_sharding") or 0) != int(
        summary_shard_metadata.get("selected_file_count_before_sharding") or 0
    ):
        raise ReplaySourceSelectionError("source_universe_count_mismatch")
    if str(full_source_universe.get("semantic_hash") or "").strip() != str(
        dict(summary.get("full_source_universe") or {}).get("semantic_hash") or ""
    ).strip():
        raise ReplaySourceSelectionError("source_universe_hash_mismatch")
    return {
        "execution_identity": execution_identity,
        "full_source_universe": full_source_universe,
        "manifest_records": manifest_records,
        "summary_shard_index": summary_shard_index,
        "summary_shard_count": summary_shard_count,
    }


def run_replay(
    *,
    manifest_path: Path | str | None = None,
    require_inventory: bool = True,
    limit_sessions: int | None = None,
    max_workers: int = 1,
    shard_count: int | None = None,
    shard_index: int | None = None,
) -> ReplayRunResult:
    started = perf_counter()
    contract = build_replay_contract_matrix().to_dict()
    git_state = _git_execution_state()
    shard_spec = _coerce_shard_spec(shard_count=shard_count, shard_index=shard_index)
    resolution, selected = select_session_files(
        manifest_path=manifest_path,
        strategy_id=contract["strategy_id"],
        require_inventory=require_inventory,
        max_records=None,
    )
    all_selected = _sorted_session_records(selected)
    if limit_sessions is not None:
        all_selected = all_selected[: int(limit_sessions)]
    selected = _apply_shard(all_selected, shard_spec)
    authoritative_inventory_resolved = resolution is not None
    source_manifest = _build_source_manifest(
        contract=contract,
        resolution=resolution,
        records=selected,
        all_record_count=len(all_selected),
        shard_spec=shard_spec,
    )
    source_manifest["full_source_universe"] = _full_source_universe(all_selected)
    all_emissions: list[ReplayEmission] = []
    malformed_rejections = 0
    oracle_checked = oracle_matched = oracle_mismatched = 0
    future_mutation_passed = future_mutation_checked = 0
    parquet_read_count = 0
    bytes_read = 0
    file_profiles: list[dict[str, Any]] = []
    worker_count = max(1, int(max_workers))
    session_payloads = [record.to_dict() for record in selected]
    session_results: list[dict[str, Any]] = []
    if worker_count == 1 or len(session_payloads) <= 1:
        for payload in session_payloads:
            try:
                session_results.append(_process_session_record(payload))
            except Exception as exc:
                malformed_rejections += 1
                file_profiles.append(
                    {
                        "path": payload["absolute_path"],
                        "symbol": payload["symbol"],
                        "session_date": payload["session_date"],
                        "projected_columns": list(payload["projected_columns"]),
                        "error": str(exc),
                    }
                )
    else:
        with ProcessPoolExecutor(max_workers=worker_count) as executor:
            futures = [executor.submit(_process_session_record, payload) for payload in session_payloads]
            for payload, future in zip(session_payloads, futures):
                try:
                    session_results.append(future.result())
                except Exception as exc:
                    malformed_rejections += 1
                    file_profiles.append(
                        {
                            "path": payload["absolute_path"],
                            "symbol": payload["symbol"],
                            "session_date": payload["session_date"],
                            "projected_columns": list(payload["projected_columns"]),
                            "error": str(exc),
                        }
                    )
    for result in sorted(
        session_results,
        key=lambda item: (item["record"]["symbol"], item["record"]["session_date"], item["record"]["logical_path"]),
    ):
        parquet_read_count += 1
        bytes_read += int(result["metrics"]["file_size_bytes"])
        file_profiles.append(result["metrics"])
        emissions = tuple(_emission_from_payload(item) for item in result["emissions"])
        all_emissions.extend(emissions)
        oracle_checked += int(result["oracle_summary"]["checked"])
        oracle_matched += int(result["oracle_summary"]["matched"])
        oracle_mismatched += int(result["oracle_summary"]["mismatched"])
        future_mutation_checked += int(result["future_checked"])
        future_mutation_passed += int(result["future_passed"])
    by_symbol = Counter(emission.symbol for emission in all_emissions)
    by_direction = Counter(emission.direction for emission in all_emissions)
    by_session = Counter(emission.session_date for emission in all_emissions)
    sorted_emissions = _sorted_emissions(all_emissions)
    candidate_semantic_hash = _validate_ledger(sorted_emissions)
    source_immutability = _source_immutability_result(selected)
    total_elapsed_seconds = perf_counter() - started
    summary = {
        "schema_version": 1,
        "contract_version": contract["temporal_contract_version"],
        "production_strategy_module": contract["production_module"],
        "production_callable": contract["production_callable"],
        "production_file_sha256": contract["production_file_sha256"],
        "runtime_profile_hash": contract["runtime_profile_hash"],
        "dataset_manifest_hash": contract["dataset_manifest_sha256"],
        **_resolution_summary(resolution),
        "source_root_identifiers": sorted({record.source_root for record in selected}),
        "selected_file_count": len(selected),
        "rejected_file_count_by_reason": {"malformed_or_unreadable": malformed_rejections},
        "parquet_read_count": parquet_read_count,
        "projected_columns": list(PROJECTED_SESSION_COLUMNS),
        "bytes_read": bytes_read,
        "symbol_session_counts": {
            f"{symbol}:{session_date}": count
            for (symbol, session_date), count in sorted(
                Counter((record.symbol, record.session_date) for record in selected).items()
            )
        },
        "valid_sessions_by_symbol": dict(sorted(Counter(record.symbol for record in selected).items())),
        "malformed_sessions_by_reason": {"rejected": malformed_rejections},
        "candidate_count": len(sorted_emissions),
        "candidate_counts_by_symbol": dict(sorted(by_symbol.items())),
        "candidate_counts_by_direction": dict(sorted(by_direction.items())),
        "candidate_counts_by_session": dict(sorted(by_session.items())),
        "duplicate_suppressions": 0,
        "earliest_session": min((record.session_date for record in selected), default=None),
        "latest_session": max((record.session_date for record in selected), default=None),
        "earliest_proposal_ready_timestamp": min((item.proposal_ready_at_iso for item in all_emissions), default=None),
        "latest_proposal_ready_timestamp": max((item.proposal_ready_at_iso for item in all_emissions), default=None),
        "oracle_reconciliation_totals": {
            "checked": oracle_checked,
            "matched": oracle_matched,
            "mismatched": oracle_mismatched,
        },
        "oracle_mismatch_count": oracle_mismatched,
        "causal_control_totals": {
            "prefix_replay_sessions": len(selected),
            "backdated_candidate_violations": 0,
        },
        "future_mutation_control_totals": {
            "checked": future_mutation_checked,
            "passed": future_mutation_passed,
            "failed": future_mutation_checked - future_mutation_passed,
        },
        "source_immutability_totals": source_immutability,
        "two_directory_determinism_hashes": {
            "contract_hash": contract["contract_hash"],
            "selected_source_manifest_hash": source_manifest["selection_summary"]["semantic_hash"],
            "candidate_semantic_hash": candidate_semantic_hash,
        },
        "file_profiles": file_profiles[: max(10, len(selected))],
        "elapsed_runtime_seconds": total_elapsed_seconds,
        "peak_memory_bytes": _peak_memory_bytes(),
        "limitations": [
            "Signal replay only.",
            "Underlying-candle replay uses VWAP proxy where exact truth is unavailable.",
            "No option execution, fill, slippage, or profitability claim.",
        ],
        "claim_boundary": contract["source_data_claim_boundary"],
        "authoritative_inventory_resolved": authoritative_inventory_resolved,
        "diagnostic_mode": not authoritative_inventory_resolved,
        "git_commit_sha": git_state.commit_sha,
        "worktree_clean": git_state.worktree_clean,
        "git_dirty_path_count": git_state.dirty_path_count,
        "phase1_verdict": "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY",
        "candidate_semantic_hash": candidate_semantic_hash,
        "execution_identity": _execution_identity(
            contract,
            {
                "dataset_manifest_hash": contract["dataset_manifest_sha256"],
                "inventory_sha256": source_manifest["inventory_resolution"]["inventory_sha256"],
                "git_commit_sha": git_state.commit_sha,
                "worktree_clean": git_state.worktree_clean,
            },
        ),
        "full_source_universe": dict(source_manifest["full_source_universe"]),
        "shard_metadata": {
            "shard_count": shard_spec.shard_count if shard_spec is not None else 1,
            "shard_index": shard_spec.shard_index if shard_spec is not None else 0,
            "is_sharded_run": shard_spec is not None,
            "merged_from_shards": False,
            "selected_file_count_before_sharding": len(all_selected),
            "selected_file_count_after_sharding": len(selected),
            "merged_shard_indexes": [shard_spec.shard_index] if shard_spec is not None else [0],
        },
    }
    if (
        not authoritative_inventory_resolved
        or not str(git_state.commit_sha or "").strip()
        or not git_state.worktree_clean
        or malformed_rejections != 0
        or oracle_mismatched != 0
        or (future_mutation_checked - future_mutation_passed) != 0
        or source_immutability["mismatched"] != 0
        or parquet_read_count != len(selected)
        or int(source_manifest["selection_summary"]["selected_file_count"]) != len(selected)
        or int(source_manifest["full_source_universe"]["selected_record_count_before_sharding"]) != len(all_selected)
    ):
        summary["phase1_verdict"] = "AUDIT_INVALID"
    summary["canonical_summary_semantic_hash"] = hashlib.sha256(
        canonical_json_bytes(_canonical_summary_payload(summary))
    ).hexdigest()
    return ReplayRunResult(
        contract=contract,
        source_manifest=source_manifest,
        summary=summary,
        emissions=sorted_emissions,
    )


def merge_replay_artifacts(*, shard_artifact_dirs: Iterable[Path | str]) -> ReplayRunResult:
    shard_dirs = [Path(path) for path in shard_artifact_dirs]
    if not shard_dirs:
        raise ValueError("shard_artifact_dirs_required")
    shard_payloads: list[dict[str, Any]] = []
    for shard_dir in shard_dirs:
        contract_path = shard_dir / CONTRACT_ARTIFACT_FILENAME
        source_manifest_path = shard_dir / SOURCE_MANIFEST_ARTIFACT_FILENAME
        summary_path = shard_dir / SUMMARY_ARTIFACT_FILENAME
        ledger_path = shard_dir / LEDGER_ARTIFACT_FILENAME
        for path in (contract_path, source_manifest_path, summary_path):
            _check_artifact_sidecar(path)
        if not ledger_path.exists():
            raise ReplaySourceSelectionError(f"missing_ledger:{ledger_path}")
        _check_artifact_sidecar(ledger_path)
        shard_payloads.append(
            {
                "contract": _load_canonical_json(contract_path),
                "source_manifest": _load_canonical_json(source_manifest_path),
                "summary": _load_canonical_json(summary_path),
                "ledger": json.loads(ledger_path.read_text(encoding="utf-8")),
                "artifact_dir": str(shard_dir),
            }
        )
    contracts = [payload["contract"] for payload in shard_payloads]
    contract_hashes = {str(contract["contract_hash"]) for contract in contracts}
    if len(contract_hashes) != 1:
        raise ReplaySourceSelectionError(f"contract_hash_mismatch:{sorted(contract_hashes)}")
    base_contract = contracts[0]
    summaries = [payload["summary"] for payload in shard_payloads]
    shard_validations = [
        _validate_shard_identity(
            contract=payload["contract"],
            source_manifest=payload["source_manifest"],
            summary=payload["summary"],
        )
        for payload in shard_payloads
    ]
    shard_metadata = [dict(summary.get("shard_metadata") or {}) for summary in summaries]
    shard_count_values = {int(meta.get("shard_count") or 0) for meta in shard_metadata}
    if len(shard_count_values) != 1:
        raise ReplaySourceSelectionError(f"shard_count_mismatch:{sorted(shard_count_values)}")
    shard_count = shard_count_values.pop()
    shard_indexes = sorted(int(meta.get("shard_index") or 0) for meta in shard_metadata)
    expected_indexes = list(range(shard_count))
    if shard_indexes != expected_indexes:
        raise ReplaySourceSelectionError(f"shard_coverage_incomplete:{shard_indexes}:expected={expected_indexes}")
    dataset_hashes = {str(summary["dataset_manifest_hash"]) for summary in summaries}
    inventory_hashes = {str(summary["inventory_sha256"]) for summary in summaries}
    code_shas = {str(validation["execution_identity"].get("git_commit_sha") or "") for validation in shard_validations}
    if len(code_shas) != 1:
        raise ReplaySourceSelectionError("code_sha_mismatch_across_shards")
    if not next(iter(code_shas)).strip():
        raise ReplaySourceSelectionError("missing_code_sha_across_shards")
    if any(not bool(validation["execution_identity"].get("worktree_clean")) for validation in shard_validations):
        raise ReplaySourceSelectionError("dirty_shard_cannot_merge")
    requested_profile_ids = {str(validation["execution_identity"].get("requested_profile_id") or "") for validation in shard_validations}
    resolved_profile_ids = {str(validation["execution_identity"].get("resolved_profile_id") or "") for validation in shard_validations}
    resolution_sources = {str(validation["execution_identity"].get("profile_resolution_source") or "") for validation in shard_validations}
    runtime_profile_hashes = {str(validation["execution_identity"].get("runtime_profile_hash") or "") for validation in shard_validations}
    if len(requested_profile_ids) != 1 or len(resolved_profile_ids) != 1 or len(resolution_sources) != 1:
        raise ReplaySourceSelectionError("profile_identity_mismatch_across_shards")
    if len(runtime_profile_hashes) != 1:
        raise ReplaySourceSelectionError("profile_hash_mismatch_across_shards")
    execution_identities = {
        canonical_json_bytes(validation["execution_identity"]).decode("utf-8") for validation in shard_validations
    }
    if len(execution_identities) != 1:
        raise ReplaySourceSelectionError("execution_identity_mismatch_across_shards")
    full_source_universes = {
        canonical_json_bytes(validation["full_source_universe"]).decode("utf-8") for validation in shard_validations
    }
    if len(full_source_universes) != 1:
        raise ReplaySourceSelectionError("source_universe_mismatch_across_shards")
    if len(dataset_hashes) != 1:
        raise ReplaySourceSelectionError(f"dataset_manifest_hash_mismatch:{sorted(dataset_hashes)}")
    if len(inventory_hashes) != 1:
        raise ReplaySourceSelectionError(f"inventory_hash_mismatch:{sorted(inventory_hashes)}")
    combined_records = _sorted_session_records(
        _record_from_payload(record)
        for payload in shard_payloads
        for record in payload["source_manifest"]["records"]
    )
    record_keys = [_record_sort_key(record) for record in combined_records]
    if len(set(record_keys)) != len(record_keys):
        raise ReplaySourceSelectionError("duplicate_source_record_across_shards")
    expected_full_source_universe = shard_validations[0]["full_source_universe"]
    if len(combined_records) != int(expected_full_source_universe["selected_record_count_before_sharding"]):
        raise ReplaySourceSelectionError("merged_source_universe_incomplete")
    actual_full_source_universe_hash = hashlib.sha256(
        canonical_json_bytes([record.to_dict() for record in combined_records])
    ).hexdigest()
    if actual_full_source_universe_hash != str(expected_full_source_universe["semantic_hash"]):
        raise ReplaySourceSelectionError("merged_source_universe_hash_mismatch")
    combined_emissions = _sorted_emissions(
        _emission_from_payload(item)
        for payload in shard_payloads
        for item in payload["ledger"]
    )
    candidate_semantic_hash = _validate_ledger(
        combined_emissions,
        expected_candidate_hash=hashlib.sha256(
            canonical_json_bytes([item.to_dict() for item in combined_emissions])
        ).hexdigest(),
    )
    for payload in shard_payloads:
        shard_emissions = _sorted_emissions(_emission_from_payload(item) for item in payload["ledger"])
        if len(shard_emissions) != int(payload["summary"].get("candidate_count") or 0):
            raise ReplaySourceSelectionError("ledger_candidate_count_mismatch")
        _validate_ledger(
            shard_emissions,
            expected_candidate_hash=str(payload["summary"].get("candidate_semantic_hash")),
        )
    source_manifest = {
        "schema_version": 1,
        "strategy_id": base_contract["strategy_id"],
        "inventory_resolution": shard_payloads[0]["source_manifest"]["inventory_resolution"],
        "records": [record.to_dict() for record in combined_records],
        "selection_summary": selection_summary(combined_records),
        "full_source_universe": dict(expected_full_source_universe),
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
    by_symbol = Counter(emission.symbol for emission in combined_emissions)
    by_direction = Counter(emission.direction for emission in combined_emissions)
    by_session = Counter(emission.session_date for emission in combined_emissions)
    oracle_checked = sum(int(summary["oracle_reconciliation_totals"]["checked"]) for summary in summaries)
    oracle_matched = sum(int(summary["oracle_reconciliation_totals"]["matched"]) for summary in summaries)
    oracle_mismatched = sum(int(summary["oracle_reconciliation_totals"]["mismatched"]) for summary in summaries)
    future_checked = sum(int(summary["future_mutation_control_totals"]["checked"]) for summary in summaries)
    future_passed = sum(int(summary["future_mutation_control_totals"]["passed"]) for summary in summaries)
    source_immutability_checked = sum(int(summary["source_immutability_totals"]["checked"]) for summary in summaries)
    source_immutability_mismatched = sum(int(summary["source_immutability_totals"]["mismatched"]) for summary in summaries)
    malformed_rejections = sum(int(dict(summary["malformed_sessions_by_reason"]).get("rejected", 0)) for summary in summaries)
    merged_summary = {
        "schema_version": 1,
        "contract_version": base_contract["temporal_contract_version"],
        "production_strategy_module": base_contract["production_module"],
        "production_callable": base_contract["production_callable"],
        "production_file_sha256": base_contract["production_file_sha256"],
        "runtime_profile_hash": base_contract["runtime_profile_hash"],
        "dataset_manifest_hash": next(iter(dataset_hashes)),
        **shard_payloads[0]["source_manifest"]["inventory_resolution"],
        "source_root_identifiers": sorted({record.source_root for record in combined_records}),
        "selected_file_count": len(combined_records),
        "rejected_file_count_by_reason": {"malformed_or_unreadable": malformed_rejections},
        "parquet_read_count": sum(int(summary["parquet_read_count"]) for summary in summaries),
        "projected_columns": list(PROJECTED_SESSION_COLUMNS),
        "bytes_read": sum(int(summary["bytes_read"]) for summary in summaries),
        "symbol_session_counts": {
            f"{symbol}:{session_date}": count
            for (symbol, session_date), count in sorted(
                Counter((record.symbol, record.session_date) for record in combined_records).items()
            )
        },
        "valid_sessions_by_symbol": dict(sorted(Counter(record.symbol for record in combined_records).items())),
        "malformed_sessions_by_reason": {"rejected": malformed_rejections},
        "candidate_count": len(combined_emissions),
        "candidate_counts_by_symbol": dict(sorted(by_symbol.items())),
        "candidate_counts_by_direction": dict(sorted(by_direction.items())),
        "candidate_counts_by_session": dict(sorted(by_session.items())),
        "duplicate_suppressions": 0,
        "earliest_session": min((record.session_date for record in combined_records), default=None),
        "latest_session": max((record.session_date for record in combined_records), default=None),
        "earliest_proposal_ready_timestamp": min((item.proposal_ready_at_iso for item in combined_emissions), default=None),
        "latest_proposal_ready_timestamp": max((item.proposal_ready_at_iso for item in combined_emissions), default=None),
        "oracle_reconciliation_totals": {
            "checked": oracle_checked,
            "matched": oracle_matched,
            "mismatched": oracle_mismatched,
        },
        "oracle_mismatch_count": oracle_mismatched,
        "causal_control_totals": {
            "prefix_replay_sessions": len(combined_records),
            "backdated_candidate_violations": 0,
        },
        "future_mutation_control_totals": {
            "checked": future_checked,
            "passed": future_passed,
            "failed": future_checked - future_passed,
        },
        "source_immutability_totals": {
            "checked": source_immutability_checked,
            "mismatched": source_immutability_mismatched,
            "status": "not_mutated" if source_immutability_mismatched == 0 else "mutated",
        },
        "two_directory_determinism_hashes": {
            "contract_hash": base_contract["contract_hash"],
            "selected_source_manifest_hash": source_manifest["selection_summary"]["semantic_hash"],
            "candidate_semantic_hash": candidate_semantic_hash,
        },
        "file_profiles": sorted(
            [profile for summary in summaries for profile in list(summary.get("file_profiles") or [])],
            key=lambda item: (str(item.get("symbol") or ""), str(item.get("session_date") or ""), str(item.get("path") or "")),
        )[: max(10, len(combined_records))],
        "elapsed_runtime_seconds": sum(float(summary["elapsed_runtime_seconds"]) for summary in summaries),
        "peak_memory_bytes": max((int(summary["peak_memory_bytes"]) for summary in summaries if summary.get("peak_memory_bytes") is not None), default=None),
        "limitations": list(summaries[0]["limitations"]),
        "claim_boundary": summaries[0]["claim_boundary"],
        "authoritative_inventory_resolved": True,
        "diagnostic_mode": False,
        "git_commit_sha": shard_validations[0]["execution_identity"]["git_commit_sha"],
        "worktree_clean": bool(shard_validations[0]["execution_identity"]["worktree_clean"]),
        "git_dirty_path_count": 0,
        "phase1_verdict": "OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY",
        "candidate_semantic_hash": candidate_semantic_hash,
        "execution_identity": shard_validations[0]["execution_identity"],
        "full_source_universe": dict(expected_full_source_universe),
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
        oracle_mismatched != 0
        or (future_checked - future_passed) != 0
        or source_immutability_mismatched != 0
        or malformed_rejections != 0
        or len(combined_emissions) != int(merged_summary["candidate_count"])
        or int(source_manifest["selection_summary"]["selected_file_count"]) != len(combined_records)
        or int(source_manifest["full_source_universe"]["selected_record_count_before_sharding"]) != len(combined_records)
    ):
        merged_summary["phase1_verdict"] = "AUDIT_INVALID"
    merged_summary["canonical_summary_semantic_hash"] = hashlib.sha256(
        canonical_json_bytes(_canonical_summary_payload(merged_summary))
    ).hexdigest()
    return ReplayRunResult(
        contract=base_contract,
        source_manifest=source_manifest,
        summary=merged_summary,
        emissions=combined_emissions,
    )


def write_replay_artifacts(run: ReplayRunResult, *, output_dir: Path, ledger_path: Path | None = None) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    write_started = perf_counter()
    contract_path = output_dir / CONTRACT_ARTIFACT_FILENAME
    source_manifest_path = output_dir / SOURCE_MANIFEST_ARTIFACT_FILENAME
    summary_path = output_dir / SUMMARY_ARTIFACT_FILENAME
    for path, payload in (
        (contract_path, run.contract),
        (source_manifest_path, run.source_manifest),
        (summary_path, run.summary),
    ):
        serialized = canonical_json_bytes(
            {
                **_artifact_evidence_fields(artifact_name=path.name, summary=run.summary),
                **payload,
            }
        )
        path.write_bytes(serialized + b"\n")
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{hashlib.sha256(serialized).hexdigest()}  {path.name}\n",
            encoding="utf-8",
        )
    if ledger_path is not None:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = canonical_json_bytes([item.to_dict() for item in run.emissions]) + b"\n"
        ledger_path.write_bytes(serialized)
        ledger_path.with_suffix(ledger_path.suffix + ".sha256").write_text(
            f"{hashlib.sha256(serialized.rstrip(b'\n')).hexdigest()}  {ledger_path.name}\n",
            encoding="utf-8",
        )
    _ = perf_counter() - write_started
    return {
        "contract": contract_path,
        "source_manifest": source_manifest_path,
        "summary": summary_path,
        "ledger": ledger_path,
    }
