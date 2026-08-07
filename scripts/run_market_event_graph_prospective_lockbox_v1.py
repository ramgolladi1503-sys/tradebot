#!/usr/bin/env python3
"""Outcome-blind prospective lockbox for the frozen Market Event Graph mechanism.

This is intentionally a thin persistence adapter around the existing read-only
MEG runtime observer.  It does not rediscover or tune the graph, calculate
returns, inspect outcomes, authorize promotion, or mutate any production path.

Each eligible session is sealed as an immutable JSON record.  The manifest is
reconstructed from sealed session files and keeps PRE_CAS and POST_CAS lanes
strictly separate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from core.market_event_graph_contract import (
    DATASET_SHA256,
    FROZEN_DISCOVERY_SPEC_SHA256,
    FROZEN_GRAPH,
    FROZEN_THRESHOLDS,
    STRATEGY_ID,
    metadata_has_frozen_contract,
    thresholds_match_frozen,
)
from core.market_event_graph_runtime_observer import observe_market_event_graph_runtime

SCHEMA_VERSION = 1
CAMPAIGN = "market_event_graph_independent_recertification_v2"
LOCKBOX = "market_event_graph_prospective_lockbox_v1"
LAST_CONSUMED_SESSION = "2026-07-22"
CAS_START = "2026-08-03"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def frozen_authority_payload() -> dict[str, Any]:
    return {
        "strategy_id": STRATEGY_ID,
        "dataset_sha256": DATASET_SHA256,
        "frozen_discovery_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "graph": list(FROZEN_GRAPH),
        "thresholds": dict(FROZEN_THRESHOLDS),
        "last_consumed_session": LAST_CONSUMED_SESSION,
        "cas_start": CAS_START,
    }


FROZEN_AUTHORITY_SHA256 = semantic_hash(frozen_authority_payload())


def classify_session(session_date: str) -> str:
    parsed = _iso_date(session_date)
    if parsed <= _iso_date(LAST_CONSUMED_SESSION):
        raise ValueError(
            f"session_not_fresh session_date={session_date} "
            f"last_consumed_session={LAST_CONSUMED_SESSION}"
        )
    return "POST_CAS" if parsed >= _iso_date(CAS_START) else "PRE_CAS_FRESH"


def milestone_for_count(session_count: int) -> str:
    count = int(session_count)
    if count < 5:
        return "OBSERVATIONAL_ONLY"
    if count < 10:
        return "OBSERVATIONAL_MILESTONE"
    if count < 20:
        return "EARLY_PROSPECTIVE_EVIDENCE"
    if count < 45:
        return "PRELIMINARY_STABILITY_REVIEW_ELIGIBLE"
    return "INDEPENDENT_CERTIFICATION_ELIGIBLE"


def seal_session(metadata: Mapping[str, Any], lockbox_dir: str | Path) -> dict[str, Any]:
    """Seal one fresh session idempotently and return the rebuilt manifest."""

    if not isinstance(metadata, Mapping):
        raise ValueError("metadata_not_mapping")
    thresholds = metadata.get("market_event_graph_thresholds")
    if not isinstance(thresholds, Mapping):
        raise ValueError("frozen_thresholds_missing")
    if not metadata_has_frozen_contract(metadata) or not thresholds_match_frozen(thresholds):
        raise ValueError("frozen_contract_mismatch")

    bars = _canonical_bars(metadata.get("completed_constituent_bars"))
    sessions = sorted({row["session_date"] for row in bars})
    if len(sessions) != 1:
        raise ValueError(f"lockbox_requires_exactly_one_session sessions={sessions}")
    session_date = sessions[0]
    regime = classify_session(session_date)

    context_ts = max(row["source_bar_end_epoch"] for row in bars)
    observer_metadata = dict(metadata)
    observer_metadata["completed_constituent_bars"] = bars
    observation = observe_market_event_graph_runtime(observer_metadata, context_ts=context_ts)
    if observation.get("session_dates") not in ([session_date], (session_date,)):
        raise ValueError(
            "observer_session_mismatch "
            f"expected={session_date} actual={observation.get('session_dates')}"
        )
    if observation.get("allowed_for_live_execution") is not False:
        raise ValueError("observer_authorization_boundary_violated")
    if observation.get("is_order_action") is not False:
        raise ValueError("observer_order_boundary_violated")
    if observation.get("broker_api_called") is not False:
        raise ValueError("observer_broker_boundary_violated")

    source_payload = {
        "completed_constituent_bars": bars,
    }
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "lockbox": LOCKBOX,
        "session_date": session_date,
        "regime": regime,
        "authority": frozen_authority_payload(),
        "frozen_authority_sha256": FROZEN_AUTHORITY_SHA256,
        "source_evidence_sha256": semantic_hash(source_payload),
        "source_interval_count": len(bars),
        "observer": _sanitize_observer(observation),
        "causal_source": source_payload,
        "policy": {
            "outcomes_opened": False,
            "performance_metrics_computed": False,
            "thresholds_tuned": False,
            "graph_rediscovered": False,
            "pre_post_cas_pooled": False,
            "independent_edge_certified": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
            "paper_authorized": False,
            "live_authorized": False,
            "order_authorized": False,
        },
    }
    record["semantic_sha256"] = semantic_hash(record)

    root = Path(lockbox_dir)
    sessions_dir = root / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    target = sessions_dir / f"{session_date}.json"
    if target.exists():
        existing = json.loads(target.read_text(encoding="utf-8"))
        _verify_record(existing)
        if existing.get("semantic_sha256") != record["semantic_sha256"]:
            raise ValueError(
                f"immutable_session_conflict session_date={session_date} "
                f"existing={existing.get('semantic_sha256')} new={record['semantic_sha256']}"
            )
    else:
        _atomic_write_json(target, record)

    manifest = rebuild_manifest(root)
    _atomic_write_json(root / "manifest.json", manifest)
    return manifest


def rebuild_manifest(lockbox_dir: str | Path) -> dict[str, Any]:
    root = Path(lockbox_dir)
    sessions_dir = root / "sessions"
    records: list[dict[str, Any]] = []
    if sessions_dir.exists():
        for path in sorted(sessions_dir.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            _verify_record(record)
            records.append(record)

    lanes: dict[str, list[dict[str, Any]]] = {"PRE_CAS_FRESH": [], "POST_CAS": []}
    dates_seen: set[str] = set()
    for record in records:
        session_date = str(record["session_date"])
        if session_date in dates_seen:
            raise ValueError(f"duplicate_session_date session_date={session_date}")
        dates_seen.add(session_date)
        expected_regime = classify_session(session_date)
        if record.get("regime") != expected_regime:
            raise ValueError(
                f"regime_mismatch session_date={session_date} "
                f"expected={expected_regime} actual={record.get('regime')}"
            )
        lanes[expected_regime].append(record)

    lane_summaries: dict[str, Any] = {}
    for regime, lane_records in lanes.items():
        count = len(lane_records)
        lane_summaries[regime] = {
            "session_count": count,
            "first_session": lane_records[0]["session_date"] if lane_records else None,
            "last_session": lane_records[-1]["session_date"] if lane_records else None,
            "milestone": milestone_for_count(count),
            "certification_session_count_gate_met": count >= 45,
            "independent_edge_certified": False,
            "session_semantic_sha256": [record["semantic_sha256"] for record in lane_records],
        }

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "campaign": CAMPAIGN,
        "lockbox": LOCKBOX,
        "principal_verdict": "MEG_PROSPECTIVE_LOCKBOX_ACCUMULATING",
        "authority": frozen_authority_payload(),
        "frozen_authority_sha256": FROZEN_AUTHORITY_SHA256,
        "total_sealed_sessions": len(records),
        "lanes": lane_summaries,
        "policy": {
            "outcome_blind": True,
            "pre_post_cas_pooled": False,
            "certification_requires_separate_evaluation": True,
            "minimum_sessions_before_certification_evaluation": 45,
            "independent_edge_certified": False,
            "options_edge_certified": False,
            "shadow_authorized": False,
            "paper_authorized": False,
            "live_authorized": False,
            "order_authorized": False,
        },
    }
    manifest["semantic_sha256"] = semantic_hash(manifest)
    return manifest


def _canonical_bars(raw_bars: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_bars, Sequence) or isinstance(raw_bars, (str, bytes)):
        raise ValueError("completed_constituent_bars_missing")
    if not raw_bars:
        raise ValueError("completed_constituent_bars_empty")

    bars: list[dict[str, Any]] = []
    prior_ts: float | None = None
    prior_source_end: float | None = None
    for raw in raw_bars:
        if not isinstance(raw, Mapping):
            raise ValueError("source_row_not_mapping")
        if raw.get("completed") is False or raw.get("is_completed") is False:
            raise ValueError("source_row_incomplete")
        session_date = str(raw.get("session_date") or "").strip()
        _iso_date(session_date)
        try:
            ts_epoch = float(raw["ts_epoch"])
            source_bar_end_epoch = float(raw.get("source_bar_end_epoch", ts_epoch))
            index_ret1 = float(raw["index_ret1"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("source_numeric_fields_invalid") from exc
        if not all(math.isfinite(value) for value in (ts_epoch, source_bar_end_epoch, index_ret1)):
            raise ValueError("source_numeric_fields_non_finite")
        if ts_epoch <= 0 or source_bar_end_epoch <= 0 or source_bar_end_epoch > ts_epoch:
            raise ValueError("source_timestamp_contract_invalid")
        if prior_ts is not None and ts_epoch <= prior_ts:
            raise ValueError("source_timestamp_not_strictly_increasing")
        if prior_source_end is not None and source_bar_end_epoch <= prior_source_end:
            raise ValueError("source_bar_end_not_strictly_increasing")
        prior_ts = ts_epoch
        prior_source_end = source_bar_end_epoch

        returns_raw = raw.get("constituent_ret1")
        if isinstance(returns_raw, Mapping):
            ordered = sorted((str(key), value) for key, value in returns_raw.items())
            returns = {key: _finite_float(value, "constituent_return_invalid") for key, value in ordered}
            participation_count = len(returns)
        elif isinstance(returns_raw, Sequence) and not isinstance(returns_raw, (str, bytes)):
            returns = [_finite_float(value, "constituent_return_invalid") for value in returns_raw]
            participation_count = len(returns)
        else:
            raise ValueError("constituent_returns_missing")
        if participation_count < int(FROZEN_THRESHOLDS["min_constituents"]):
            raise ValueError("constituent_coverage_below_frozen_minimum")

        row: dict[str, Any] = {
            "session_date": session_date,
            "ts_epoch": ts_epoch,
            "source_bar_end_epoch": source_bar_end_epoch,
            "completed": True,
            "index_ret1": index_ret1,
            "constituent_ret1": returns,
        }
        if raw.get("index_close") is not None:
            row["index_close"] = _finite_float(raw.get("index_close"), "index_close_invalid")
        bars.append(row)
    return bars


def _sanitize_observer(observation: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "schema_version",
        "strategy_id",
        "status",
        "reason",
        "source_interval_count",
        "accepted_interval_count",
        "rejected_interval_count",
        "rejection_counts",
        "label_counts",
        "partial_sequence_length",
        "partial_sequence_labels",
        "graph_trigger_count",
        "producer_status",
        "adapter_status",
        "adapter_row_count",
        "latest_source_bar_end_epoch",
        "latest_source_age_sec",
        "source_fresh",
        "session_dates",
        "allowed_for_live_execution",
        "is_order_action",
        "broker_api_called",
    )
    return {key: observation.get(key) for key in allowed}


def _verify_record(record: Mapping[str, Any]) -> None:
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("sealed_record_schema_mismatch")
    if record.get("campaign") != CAMPAIGN or record.get("lockbox") != LOCKBOX:
        raise ValueError("sealed_record_identity_mismatch")
    if record.get("frozen_authority_sha256") != FROZEN_AUTHORITY_SHA256:
        raise ValueError("sealed_record_authority_mismatch")
    actual = record.get("semantic_sha256")
    material = {key: value for key, value in record.items() if key != "semantic_sha256"}
    if actual != semantic_hash(material):
        raise ValueError("sealed_record_semantic_hash_mismatch")
    policy = record.get("policy")
    if not isinstance(policy, Mapping):
        raise ValueError("sealed_record_policy_missing")
    forbidden_true = (
        "outcomes_opened",
        "performance_metrics_computed",
        "thresholds_tuned",
        "graph_rediscovered",
        "pre_post_cas_pooled",
        "independent_edge_certified",
        "options_edge_certified",
        "shadow_authorized",
        "paper_authorized",
        "live_authorized",
        "order_authorized",
    )
    if any(policy.get(key) is not False for key in forbidden_true):
        raise ValueError("sealed_record_policy_boundary_violated")


def _finite_float(value: Any, reason: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if not math.isfinite(parsed):
        raise ValueError(reason)
    return parsed


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"invalid_session_date value={value!r}") from exc


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--lockbox-dir", type=Path, required=True)
    args = parser.parse_args()

    metadata = json.loads(args.metadata_json.read_text(encoding="utf-8"))
    manifest = seal_session(metadata, args.lockbox_dir)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
