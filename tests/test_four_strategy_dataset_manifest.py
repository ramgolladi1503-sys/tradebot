from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pandas as pd

from research.strategy_validation.data_suitability import (
    build_four_strategy_dataset_manifest,
    discover_candidate_datasets,
    inspect_dataset,
    load_frozen_contract_bundle,
    write_manifest_and_sidecar,
)


REAL_CANDLE = Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet")
REAL_TICK = Path("/Users/madhuram/tradebot/.runtime/market_data/ticks_20260707_132935.parquet")
REPO_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = REPO_ROOT / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json"


def _write_sample_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def test_load_frozen_contract_bundle_matches_sidecar() -> None:
    bundle = load_frozen_contract_bundle(BUNDLE)
    assert bundle["architecture_decision"] == "KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE"
    assert bundle["bundle_id"] == "four_strategy_contract_bundle_v1"


def test_real_candle_file_is_complete_but_cannot_prove_vwap_truth() -> None:
    inspection = inspect_dataset(REAL_CANDLE, bundle=load_frozen_contract_bundle(BUNDLE))

    assert inspection.data_kind == "CANDLE_OHLCV"
    assert inspection.session_integrity.status == "COMPLETE"
    assert inspection.volume_truth_status == "ZERO_VOLUME"
    assert inspection.field_coverage[2].field == "vwap"
    assert inspection.field_coverage[2].status == "UNAVAILABLE"
    opening = next(item for item in inspection.strategy_coverage if item.strategy_id == "opening_range_retest_v1")
    assert opening.status == "INVALID_DUE_TO_DATA"
    assert "vwap" in opening.blocking_required_fields


def test_real_tick_file_has_volume_but_no_completed_bar_history() -> None:
    inspection = inspect_dataset(REAL_TICK, bundle=load_frozen_contract_bundle(BUNDLE))

    assert inspection.data_kind == "TICK_QUOTE"
    completed = next(item for item in inspection.field_coverage if item.field == "completed_bar_history")
    assert completed.status == "UNAVAILABLE"
    vwap = next(item for item in inspection.field_coverage if item.field == "vwap")
    assert vwap.status == "DERIVABLE"
    assert inspection.volume_truth_status == "HAS_VOLUME"
    trend = next(item for item in inspection.strategy_coverage if item.strategy_id == "trend_pullback_v1")
    assert trend.status == "INVALID_DUE_TO_DATA"
    assert "completed_bar_history" in trend.blocking_required_fields


def test_manifest_builder_is_deterministic_and_excludes_metadata_dirs(tmp_path: Path) -> None:
    candle = _write_sample_parquet(
        tmp_path / "dataset" / "candles.parquet",
        pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-07-09 09:15:00"),
                    "symbol": "NSE_INDEX|Nifty 50",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 0.0,
                    "interval": "1minute",
                },
                {
                    "timestamp": pd.Timestamp("2026-07-09 09:16:00"),
                    "symbol": "NSE_INDEX|Nifty 50",
                    "open": 1.5,
                    "high": 2.5,
                    "low": 1.25,
                    "close": 2.0,
                    "volume": 0.0,
                    "interval": "1minute",
                },
            ]
        ),
    )
    tick = _write_sample_parquet(
        tmp_path / "dataset" / "ticks.parquet",
        pd.DataFrame(
            [
                {"ts": 1783411178.0, "symbol": "SENSEX", "ltp": 10.0, "bid": 9.5, "ask": 10.5, "vol": 25.0},
                {"ts": 1783411179.0, "symbol": "SENSEX", "ltp": 10.5, "bid": 10.0, "ask": 11.0, "vol": 30.0},
            ]
        ),
    )
    (tmp_path / "dataset" / "manifests").mkdir(parents=True)
    (tmp_path / "dataset" / "manifests" / "skip.json").write_text("{}", encoding="utf-8")

    discovered = discover_candidate_datasets([tmp_path])
    assert candle in discovered
    assert tick in discovered
    assert not any("manifests" in path.parts for path in discovered)

    manifest_1 = build_four_strategy_dataset_manifest(roots=[tmp_path], bundle_path=BUNDLE, code_commit="deadbeef")
    manifest_2 = build_four_strategy_dataset_manifest(roots=[tmp_path], bundle_path=BUNDLE, code_commit="deadbeef")
    assert manifest_1 == manifest_2
    assert manifest_1["corpus_status"] == "INVALID_DUE_TO_DATA"
    assert manifest_1["dataset_count"] >= 2
    assert manifest_1["strategy_summary"]["opening_range_retest_v1"]["status"] == "INVALID_DUE_TO_DATA"
    assert "vwap" in manifest_1["strategy_summary"]["opening_range_retest_v1"]["blocking_required_fields"]

    out_path = tmp_path / "four_strategy_dataset_manifest_v1.json"
    json_path, sidecar_path = write_manifest_and_sidecar(manifest_1, output_path=out_path)
    assert json_path.exists()
    assert sidecar_path.exists()
    expected_hash = hashlib.sha256((json.dumps(manifest_1, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")).hexdigest()
    assert sidecar_path.read_text(encoding="utf-8").split()[0] == expected_hash


def test_malformed_parquet_file_is_recorded_as_unverifiable(tmp_path: Path) -> None:
    bad = tmp_path / "broken.parquet"
    bad.write_text("not parquet", encoding="utf-8")

    manifest = build_four_strategy_dataset_manifest(roots=[tmp_path], bundle_path=BUNDLE, code_commit="deadbeef")
    rows = [row for row in manifest["dataset_records"] if row["absolute_path"] == str(bad.resolve())]

    assert len(rows) == 1
    row = rows[0]
    assert row["suitability_status"] == "INVALID_OR_UNVERIFIABLE"
    assert row["inspection_error"]
    assert row["exclusion_reason"].startswith("read_error:")
