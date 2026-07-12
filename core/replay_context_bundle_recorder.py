from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from core.replay_context_recorder import build_replay_context_record

REPLAY_CONTEXT_BUNDLE_SCHEMA_VERSION = 1
REPLAY_CONTEXT_BUNDLE_SOURCE = "replay_context_bundle_recorder_v1"


def replay_context_bundle_dir(output_root: Path | str | None, run_id: str) -> Path:
    root = Path(output_root).expanduser() if output_root is not None else Path(".runtime") / "replay_context_bundles"
    return root / run_id


def replay_context_bundle_path(*, output_root: Path | str | None, run_id: str, bundle_id: str, latest: bool = False) -> Path:
    bundle_dir = replay_context_bundle_dir(output_root, run_id)
    if latest:
        return bundle_dir / "replay_context_bundle_latest.json"
    return bundle_dir / f"replay_context_bundle_{bundle_id}.json"


def build_replay_context_bundle_record(
    *,
    replay_bundle_id: str,
    replay_event_id: str | None,
    source_path: str | Path | None,
    source_row_index: int | None,
    source_timestamp_epoch: Any | None,
    raw_row: Mapping[str, Any] | None,
    normalized_snapshot: Mapping[str, Any] | None,
    strategy_context: Any | None,
    report: Any | None,
    strategy_id: str | None,
    source_file_sha256: str | None = None,
    source_row_sha256: str | None = None,
) -> dict[str, Any]:
    raw_row_dict = dict(raw_row or {})
    normalized_snapshot_dict = dict(normalized_snapshot or {})
    strategy_context_dict = _to_mapping(strategy_context)
    report_dict = _report_summary(report)
    candidate_pool_summary = _candidate_pool_summary(report)
    ranking_summary = _ranking_summary(report)

    source_timestamp = _first_present(
        raw_row_dict,
        "source_timestamp",
        "source_timestamp_utc",
        "timestamp",
        "ts_ist",
    )
    if source_timestamp_epoch in (None, "", "None"):
        source_timestamp_epoch = _first_present(
            raw_row_dict,
            "source_timestamp_epoch",
            "timestamp_epoch",
            "ts_epoch",
            "ts",
        )

    bundle_context = {
        **raw_row_dict,
        **normalized_snapshot_dict,
        **strategy_context_dict,
        **report_dict,
    }
    for key in ("quote_source", "quote_age_sec"):
        value = raw_row_dict.get(key)
        if value not in (None, "", "None"):
            bundle_context[key] = value
    replay_context = build_replay_context_record(
        bundle_context,
        source=REPLAY_CONTEXT_BUNDLE_SOURCE,
        require_candidate_pool_inputs=True,
    )
    bundle_blockers = list(replay_context.get("replay_context_blockers") or [])
    if source_path in (None, "", "None"):
        bundle_blockers.append("missing_source_path")
    if replay_event_id in (None, "", "None"):
        bundle_blockers.append("missing_replay_event_id")
    if source_timestamp_epoch in (None, "", "None") and source_timestamp in (None, "", "None"):
        bundle_blockers.append("missing_source_timestamp")
    if not normalized_snapshot_dict:
        bundle_blockers.append("missing_normalized_snapshot")
    if not strategy_context_dict:
        bundle_blockers.append("missing_strategy_context")

    bundle_blockers = list(dict.fromkeys(bundle_blockers))
    bundle_ready = not bundle_blockers

    bundle = {
        "schema_version": REPLAY_CONTEXT_BUNDLE_SCHEMA_VERSION,
        "replay_bundle_id": replay_bundle_id,
        "replay_event_id": replay_event_id,
        "source_path": str(source_path) if source_path not in (None, "", "None") else None,
        "source_row_index": source_row_index,
        "source_timestamp": source_timestamp,
        "source_timestamp_epoch": source_timestamp_epoch,
        "source_file_sha256": source_file_sha256,
        "source_row_sha256": source_row_sha256,
        "replay_context_bundle_source": REPLAY_CONTEXT_BUNDLE_SOURCE,
        "replay_context_bundle_ready": bundle_ready,
        "replay_context_bundle_blockers": bundle_blockers,
        "replay_context_ready": bool(replay_context.get("replay_context_ready")),
        "replay_context_blockers": list(replay_context.get("replay_context_blockers") or []),
        "replay_context_source": replay_context.get("replay_context_source"),
        "replay_context": replay_context.get("replay_context"),
        "normalized_snapshot": normalized_snapshot_dict,
        "strategy_context": strategy_context_dict,
        "strategy_id": strategy_id,
        "candidate_pool_summary": candidate_pool_summary,
        "ranking_summary": ranking_summary,
        "report_summary": report_dict,
        "read_only": True,
        "append": False,
        "is_order_action": False,
        "broker_api_called": False,
        "live_feed_used": False,
        "production_artifacts_written": False,
    }
    return bundle


def write_replay_context_bundle_evidence(
    *,
    output_root: Path | str | None,
    run_id: str,
    bundle_id: str,
    replay_event_id: str | None,
    source_path: str | Path | None,
    source_row_index: int | None,
    source_timestamp_epoch: Any | None,
    raw_row: Mapping[str, Any] | None,
    normalized_snapshot: Mapping[str, Any] | None,
    strategy_context: Any | None,
    report: Any | None,
    strategy_id: str | None,
    source_file_sha256: str | None = None,
    source_row_sha256: str | None = None,
) -> Path:
    payload = build_replay_context_bundle_record(
        replay_bundle_id=bundle_id,
        replay_event_id=replay_event_id,
        source_path=source_path,
        source_row_index=source_row_index,
        source_timestamp_epoch=source_timestamp_epoch,
        raw_row=raw_row,
        normalized_snapshot=normalized_snapshot,
        strategy_context=strategy_context,
        report=report,
        strategy_id=strategy_id,
        source_file_sha256=source_file_sha256,
        source_row_sha256=source_row_sha256,
    )
    bundle_dir = replay_context_bundle_dir(output_root, run_id)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    latest_path = replay_context_bundle_path(output_root=output_root, run_id=run_id, bundle_id=bundle_id, latest=True)
    event_path = replay_context_bundle_path(output_root=output_root, run_id=run_id, bundle_id=bundle_id, latest=False)
    text = json.dumps(payload, indent=2, sort_keys=True, default=str)
    latest_path.write_text(text, encoding="utf-8")
    event_path.write_text(text, encoding="utf-8")
    return event_path


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_dict"):
        try:
            result = value.to_dict()
        except Exception:
            return {}
        if isinstance(result, Mapping):
            return dict(result)
    return {}


def _candidate_pool_summary(report: Any) -> dict[str, Any]:
    candidate_pool = getattr(report, "candidate_pool", None)
    if candidate_pool is None:
        return {}
    return _to_mapping(candidate_pool)


def _ranking_summary(report: Any) -> dict[str, Any]:
    ranking = getattr(report, "ranking", None)
    if ranking is None:
        return {}
    return _to_mapping(ranking)


def _report_summary(report: Any) -> dict[str, Any]:
    if report is None:
        return {}
    payload = {}
    field_map = {
        "schema_version": "schema_version",
        "symbol": "symbol",
        "read_only": "read_only",
        "append": "append",
        "raw_candidate_count": "raw_candidate_count",
        "normalized_candidate_count": "normalized_candidate_count",
        "ranked_candidate_count": "ranked_candidate_count",
        "top_rank_strategy_id": "top_rank_strategy_id",
        "top_rank_score": "top_rank_score",
        "executable_rank_count": "executable_rank_count",
        "rankable_candidates": "rankable_candidates",
        "feed_blocked_candidates": "feed_blocked_candidates",
        "fallback_blocked_candidates": "fallback_blocked_candidates",
        "stale_blocked_candidates": "stale_blocked_candidates",
        "real_bid_ask_candidates": "real_bid_ask_candidates",
        "mocked_from_ltp_candidates": "mocked_from_ltp_candidates",
        "executable_fallback_violations": "executable_fallback_violations",
        "blockers": "blockers",
        "warnings": "warnings",
        "safety_flags": "safety_flags",
        "generated_epoch": "generated_epoch",
    }
    for key in field_map.values():
        value = getattr(report, key, None)
        if value is not None:
            payload[key] = value
    candidate_pool = _candidate_pool_summary(report)
    payload["trade_builder_raw_count"] = getattr(report, "raw_candidate_count", None)
    payload["top_opportunities_source_candidate_count"] = candidate_pool.get("candidate_count")
    payload["top_opportunities_executable_count"] = getattr(report, "executable_rank_count", None)
    payload["ranked_total_count"] = getattr(report, "ranked_candidate_count", None)
    payload["ranked_executable_count"] = getattr(report, "executable_rank_count", None)
    payload["phase2_input_count"] = getattr(report, "raw_candidate_count", None)
    return payload


def _first_present(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", "None"):
            return value
    return None


def sha256_file(path: Path | str) -> str:
    file_path = Path(path).expanduser()
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "REPLAY_CONTEXT_BUNDLE_SCHEMA_VERSION",
    "REPLAY_CONTEXT_BUNDLE_SOURCE",
    "build_replay_context_bundle_record",
    "replay_context_bundle_dir",
    "replay_context_bundle_path",
    "sha256_file",
    "write_replay_context_bundle_evidence",
]
