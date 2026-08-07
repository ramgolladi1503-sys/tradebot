#!/usr/bin/env python3
"""Extract one fresh outcome-blind MEG session from governed live-source JSONL.

This is a bridge, not a collector. It consumes rows already written by the
read-only Market Event Graph live-source stack and assembles only the causal
completed-bar fields required by the prospective lockbox. It never subscribes,
fetches, tunes, computes outcomes, or authorizes execution.
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
    FROZEN_THRESHOLDS,
    STRATEGY_ID,
    metadata_has_frozen_contract,
    thresholds_match_frozen,
)

SOURCE_KIND = "LIVE_CAPTURED_METADATA"
LAST_CONSUMED_SESSION = "2026-07-22"
CAS_START = "2026-08-03"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def semantic_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_session(session_date: str) -> str:
    parsed = date.fromisoformat(session_date)
    if parsed <= date.fromisoformat(LAST_CONSUMED_SESSION):
        raise ValueError(f"session_not_fresh:{session_date}")
    return "POST_CAS" if parsed >= date.fromisoformat(CAS_START) else "PRE_CAS_FRESH"


def _finite_float(value: Any, reason: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(reason) from exc
    if not math.isfinite(parsed):
        raise ValueError(reason)
    return parsed


def _validate_source_row(row: Mapping[str, Any], *, session_date: str) -> dict[str, Any]:
    if str(row.get("source_kind") or "") != SOURCE_KIND:
        raise ValueError("source_kind_not_live_captured_metadata")
    if str(row.get("session_date") or "") != session_date:
        raise ValueError("source_session_mismatch")
    if row.get("read_only") is not True:
        raise ValueError("source_not_read_only")
    if row.get("is_order_action") is not False:
        raise ValueError("source_order_boundary_violated")
    if row.get("broker_api_called") is not False:
        raise ValueError("source_broker_boundary_violated")
    if row.get("allowed_for_live_execution") is not False:
        raise ValueError("source_live_authority_violated")
    thresholds = row.get("market_event_graph_thresholds")
    if not isinstance(thresholds, Mapping):
        raise ValueError("source_frozen_thresholds_missing")
    if not metadata_has_frozen_contract(row) or not thresholds_match_frozen(thresholds):
        raise ValueError("source_frozen_contract_mismatch")

    bars = row.get("completed_constituent_bars")
    if not isinstance(bars, Sequence) or isinstance(bars, (str, bytes)) or len(bars) != 1:
        raise ValueError("source_requires_one_completed_interval")
    raw_bar = bars[0]
    if not isinstance(raw_bar, Mapping):
        raise ValueError("source_completed_interval_not_mapping")
    if raw_bar.get("completed") is not True or raw_bar.get("is_completed") is False:
        raise ValueError("source_completed_interval_not_complete")
    if str(raw_bar.get("session_date") or "") != session_date:
        raise ValueError("source_bar_session_mismatch")

    ts_epoch = _finite_float(raw_bar.get("ts_epoch"), "source_bar_ts_invalid")
    source_end = _finite_float(
        raw_bar.get("source_bar_end_epoch", ts_epoch), "source_bar_end_invalid"
    )
    index_ret1 = _finite_float(raw_bar.get("index_ret1"), "source_index_return_invalid")
    if ts_epoch <= 0 or source_end <= 0 or source_end > ts_epoch:
        raise ValueError("source_timestamp_contract_invalid")

    returns_raw = raw_bar.get("constituent_ret1")
    if isinstance(returns_raw, Mapping):
        returns: dict[str, float] | list[float] = {
            str(key): _finite_float(value, "source_constituent_return_invalid")
            for key, value in sorted(returns_raw.items(), key=lambda item: str(item[0]))
        }
        participation = len(returns)
    elif isinstance(returns_raw, Sequence) and not isinstance(returns_raw, (str, bytes)):
        returns = [
            _finite_float(value, "source_constituent_return_invalid") for value in returns_raw
        ]
        participation = len(returns)
    else:
        raise ValueError("source_constituent_returns_missing")
    if participation < int(FROZEN_THRESHOLDS["min_constituents"]):
        raise ValueError("source_constituent_coverage_below_frozen_minimum")

    expected = int(row.get("expected_constituents") or 0)
    if expected < int(FROZEN_THRESHOLDS["min_constituents"]):
        raise ValueError("source_expected_constituents_below_frozen_minimum")
    if participation != expected:
        raise ValueError("source_constituent_count_mismatch")

    bar: dict[str, Any] = {
        "session_date": session_date,
        "ts_epoch": ts_epoch,
        "source_bar_end_epoch": source_end,
        "completed": True,
        "index_ret1": index_ret1,
        "constituent_ret1": returns,
    }
    if raw_bar.get("index_close") is not None:
        bar["index_close"] = _finite_float(raw_bar.get("index_close"), "source_index_close_invalid")
    return bar


def extract_governed_session(
    source_jsonl: str | Path, *, session_date: str
) -> dict[str, Any]:
    source = Path(source_jsonl)
    if not source.is_file():
        raise FileNotFoundError(source)
    regime = classify_session(session_date)

    selected: list[tuple[dict[str, Any], dict[str, Any]]] = []
    with source.open("r", encoding="utf-8") as handle:
        for lineno, raw in enumerate(handle, start=1):
            text = raw.strip()
            if not text:
                continue
            value = json.loads(text)
            if not isinstance(value, Mapping):
                raise ValueError(f"source_row_not_mapping:{lineno}")
            row = dict(value)
            if str(row.get("session_date") or "") != session_date:
                continue
            bar = _validate_source_row(row, session_date=session_date)
            selected.append((row, bar))

    if not selected:
        raise ValueError(f"no_governed_rows_for_session:{session_date}")

    run_ids = {str(row.get("run_id") or "") for row, _ in selected}
    if "" in run_ids or len(run_ids) != 1:
        raise ValueError(f"mixed_or_missing_run_ids:{sorted(run_ids)}")
    universe_hashes = {str(row.get("universe_hash") or "") for row, _ in selected}
    if "" in universe_hashes or len(universe_hashes) != 1:
        raise ValueError("mixed_or_missing_universe_hashes")
    expected_counts = {int(row.get("expected_constituents") or 0) for row, _ in selected}
    if len(expected_counts) != 1:
        raise ValueError("mixed_expected_constituent_counts")

    selected.sort(key=lambda item: item[1]["source_bar_end_epoch"])
    bars: list[dict[str, Any]] = []
    prior_ts: float | None = None
    source_row_hashes: list[str] = []
    for row, bar in selected:
        current = float(bar["source_bar_end_epoch"])
        if prior_ts is not None and current <= prior_ts:
            raise ValueError("duplicate_or_nonincreasing_source_interval")
        prior_ts = current
        bars.append(bar)
        source_row_hashes.append(semantic_hash(row))

    metadata: dict[str, Any] = {
        "market_event_graph_strategy_id": STRATEGY_ID,
        "market_event_graph_dataset_sha256": DATASET_SHA256,
        "market_event_graph_frozen_spec_sha256": FROZEN_DISCOVERY_SPEC_SHA256,
        "market_event_graph_thresholds": dict(FROZEN_THRESHOLDS),
        "completed_constituent_bars": bars,
        "governed_source_bridge": {
            "schema_version": 1,
            "source_kind": SOURCE_KIND,
            "source_path": str(source.resolve()),
            "source_file_sha256": file_sha256(source),
            "source_session_date": session_date,
            "source_regime": regime,
            "source_run_id": next(iter(run_ids)),
            "source_universe_hash": next(iter(universe_hashes)),
            "source_expected_constituents": next(iter(expected_counts)),
            "source_interval_count": len(bars),
            "source_row_semantic_sha256": source_row_hashes,
            "outcomes_opened": False,
            "performance_metrics_computed": False,
            "thresholds_tuned": False,
            "graph_rediscovered": False,
        },
        "read_only": True,
        "is_order_action": False,
        "broker_api_called": False,
        "allowed_for_live_execution": False,
    }
    metadata["governed_source_bridge"]["extracted_metadata_semantic_sha256"] = semantic_hash(
        {key: value for key, value in metadata.items() if key != "governed_source_bridge"}
    )
    return metadata


def atomic_write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp, target)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", required=True)
    parser.add_argument("--session-date", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    payload = extract_governed_session(args.source_jsonl, session_date=args.session_date)
    atomic_write_json(args.output_json, payload)
    print(
        json.dumps(
            {
                "principal_verdict": "MEG_GOVERNED_SESSION_METADATA_EXTRACTED",
                "session_date": args.session_date,
                "regime": payload["governed_source_bridge"]["source_regime"],
                "source_interval_count": len(payload["completed_constituent_bars"]),
                "source_file_sha256": payload["governed_source_bridge"]["source_file_sha256"],
                "outcomes_opened": False,
                "performance_metrics_computed": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
