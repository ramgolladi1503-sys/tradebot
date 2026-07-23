from __future__ import annotations

import hashlib
import json
import subprocess
import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

from research.strategy_validation import (
    build_four_strategy_dataset_manifest_v2,
    build_upstox_corpus_inventory,
    inspect_dataset,
    load_frozen_contract_bundle,
    write_inventory_and_sidecar,
    write_v2_manifest_and_sidecar,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOTS = [
    REPO_ROOT / "runtime" / "upstox_candidate_replay",
    REPO_ROOT / ".runtime" / "market_data",
]
BUNDLE = REPO_ROOT / "docs" / "agent_reviews" / "four_strategy_contract_bundle_v1.json"
V1_MANIFEST = REPO_ROOT / "docs" / "agent_reviews" / "four_strategy_dataset_manifest_v1.json"
REAL_CANDLE_CANDIDATES = [
    REPO_ROOT / "runtime" / "upstox_candidate_replay" / "20260709" / "underlying" / "NSE_INDEX|Nifty 50_20260709.parquet",
    Path("/Users/madhuram/tradebot/runtime/upstox_candidate_replay/20260709/underlying/NSE_INDEX|Nifty 50_20260709.parquet"),
]
REAL_TICK_CANDIDATES = [
    REPO_ROOT / "runtime" / "market_data" / "upstox" / "20260714" / "ticks_1784016031.parquet",
    REPO_ROOT / ".runtime" / "market_data" / "ticks_20260707_132935.parquet",
    Path("/Users/madhuram/tradebot/.runtime/market_data/ticks_20260707_132935.parquet"),
]


def _first_existing_path(candidates: list[Path], *, description: str) -> Path:
    for path in candidates:
        if path.exists():
            return path
    pytest.skip(f"{description} is unavailable in this checkout")


def _write_parquet(path: Path, frame: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path


def _previous_manifest_for_temp_fixture(temp_dir: Path, current_file: Path, removed_file: Path) -> Path:
    payload = {
        "schema_version": 1,
        "dataset_records": [
            {
                "absolute_path": str(current_file.resolve()),
                "relative_path": str(current_file.resolve()),
                "sha256": "deadbeef",
                "file_size_bytes": 1,
                "quality_status": "INVALID",
                "suitability_status": "INVALID_DUE_TO_DATA",
                "timestamp_min": "2026-07-16T09:15:00",
                "data_kind": "CANDLE_OHLCV",
                "file_format": "parquet",
            },
            {
                "absolute_path": str(removed_file.resolve()),
                "relative_path": str(removed_file.resolve()),
                "sha256": "removed",
                "file_size_bytes": 1,
                "quality_status": "ACCEPTED",
                "suitability_status": "SUITABLE",
                "timestamp_min": "2026-07-15T09:15:00",
                "data_kind": "CANDLE_OHLCV",
                "file_format": "parquet",
            },
        ],
    }
    prev = temp_dir / "previous_manifest.json"
    prev.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return prev


@pytest.fixture(scope="module")
def bundle() -> dict[str, object]:
    return load_frozen_contract_bundle(BUNDLE)


@pytest.fixture(scope="module")
def live_inventory(bundle: dict[str, object]) -> dict[str, object]:
    available_roots = [path for path in ROOTS if path.exists()]
    if len(available_roots) < len(ROOTS):
        pytest.skip("required Upstox corpus roots are unavailable in this checkout")
    return build_upstox_corpus_inventory(
        roots=available_roots,
        bundle_path=BUNDLE,
        previous_manifest_path=V1_MANIFEST,
        code_commit="deadbeef",
    )


@pytest.fixture(scope="module")
def live_manifest(live_inventory: dict[str, object]) -> dict[str, object]:
    return build_four_strategy_dataset_manifest_v2(
        roots=ROOTS,
        bundle_path=BUNDLE,
        previous_manifest_path=V1_MANIFEST,
        inventory=live_inventory,
        code_commit="deadbeef",
    )


def test_frozen_contract_bundle_matches_sidecar(bundle: dict[str, object]) -> None:
    assert bundle["architecture_decision"] == "KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE"
    assert bundle["bundle_id"] == "four_strategy_contract_bundle_v1"


def test_real_candle_and_tick_truth_prove_current_field_classification(bundle: dict[str, object]) -> None:
    candle = inspect_dataset(_first_existing_path(REAL_CANDLE_CANDIDATES, description="real candle corpus file"), bundle=bundle)
    tick = inspect_dataset(_first_existing_path(REAL_TICK_CANDIDATES, description="real tick corpus file"), bundle=bundle)

    assert candle.data_kind == "CANDLE_OHLCV"
    assert candle.session_integrity.status == "FULL_SESSION"
    assert candle.volume_truth_status == "ZERO_VOLUME"
    assert candle.field_coverage[2].field == "vwap"
    assert candle.field_coverage[2].status == "UNAVAILABLE"

    assert tick.data_kind in {"TICK_QUOTE", "TICK_STREAM"}
    if tick.data_kind == "TICK_QUOTE":
        assert tick.volume_truth_status == "HAS_VOLUME"
    else:
        assert tick.volume_truth_status == "PARTIAL_VOLUME"
    vwap = next(item for item in tick.field_coverage if item.field == "vwap")
    if tick.data_kind == "TICK_QUOTE":
        assert vwap.status in {"DERIVABLE", "DIRECT"}
    else:
        assert vwap.status == "UNAVAILABLE"


def test_incremental_inventory_detects_new_session_and_rejects_cache_artifacts(tmp_path: Path) -> None:
    current = _write_parquet(
        tmp_path / "dataset" / "20260716" / "underlying" / "NSE_INDEX|Nifty 50_20260716.parquet",
        pd.DataFrame(
            [
                {
                    "timestamp": pd.Timestamp("2026-07-16 09:15:00"),
                    "symbol": "NSE_INDEX|Nifty 50",
                    "open": 1.0,
                    "high": 2.0,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 0.0,
                    "oi": 0.0,
                    "source": "upstox",
                    "interval": "1minute",
                    "fetch_timestamp": pd.Timestamp("2026-07-16 17:00:00"),
                    "fetch_start_date": "2026-07-16",
                    "fetch_end_date": "2026-07-16",
                    "data_origin": "upstox_api",
                    "synthetic": False,
                    "mock": False,
                    "fallback": False,
                    "provider": "upstox",
                    "source_endpoint": "/v3/historical-candle/NIFTY/1minute/2026-07-16/2026-07-16",
                },
                {
                    "timestamp": pd.Timestamp("2026-07-16 09:16:00"),
                    "symbol": "NSE_INDEX|Nifty 50",
                    "open": 1.5,
                    "high": 2.5,
                    "low": 1.25,
                    "close": 2.0,
                    "volume": 0.0,
                    "oi": 0.0,
                    "source": "upstox",
                    "interval": "1minute",
                    "fetch_timestamp": pd.Timestamp("2026-07-16 17:00:00"),
                    "fetch_start_date": "2026-07-16",
                    "fetch_end_date": "2026-07-16",
                    "data_origin": "upstox_api",
                    "synthetic": False,
                    "mock": False,
                    "fallback": False,
                    "provider": "upstox",
                    "source_endpoint": "/v3/historical-candle/NIFTY/1minute/2026-07-16/2026-07-16",
                },
            ]
        ),
    )
    duplicate = tmp_path / "dataset" / "20260716" / "underlying" / "NSE_INDEX|Nifty 50_20260716_copy.parquet"
    shutil.copyfile(current, duplicate)
    removed = tmp_path / "dataset" / "20260715" / "underlying" / "NSE_INDEX|Nifty 50_20260715.parquet"
    removed.parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "dataset" / ".DS_Store").write_text("cache", encoding="utf-8")
    (tmp_path / "dataset" / "ticks_20260705.jsonl").write_text("", encoding="utf-8")
    _option_quote = _write_parquet(
        tmp_path / "dataset" / "20260709" / "options" / "BANKNIFTY 56400 CE 28 JUL 26.parquet",
        pd.DataFrame(
            [
                {"ts": 1783420000.0, "symbol": "BANKNIFTY 56400 CE 28 JUL 26", "ltp": 100.0, "bid": 99.5, "ask": 100.5, "vol": 10.0},
                {"ts": 1783420060.0, "symbol": "BANKNIFTY 56400 CE 28 JUL 26", "ltp": 101.0, "bid": 100.5, "ask": 101.5, "vol": 12.0},
            ]
        ),
    )
    _option_depth = _write_parquet(
        tmp_path / "dataset" / "20260709" / "options" / "BANKNIFTY 56400 CE 28 JUL 26_depth.parquet",
        pd.DataFrame(
            [
                {"ts": 1783420000.0, "symbol": "BANKNIFTY 56400 CE 28 JUL 26", "ltp": 100.0, "bid": 99.5, "ask": 100.5, "vol": 10.0, "depth": 4},
            ]
        ),
    )
    fetch_manifest = tmp_path / "dataset" / "20260716" / "manifests" / "upstox_fetch_manifest_20260716.json"
    fetch_manifest.parent.mkdir(parents=True, exist_ok=True)
    fetch_manifest.write_text(
        json.dumps(
            {
                "date": "20260716",
                "provider": "upstox",
                "capture_timestamp": "2026-07-17T23:47:06.572530",
                "data_type": "UPSTOX_OPTION_CANDLE_ONLY",
                "fetch_status": "UPSTOX_FETCH_SUCCEEDED_REAL_CANDLES",
                "data_origin": "upstox_api",
                "synthetic": False,
                "mock": False,
                "fallback": False,
                "token_logged": False,
                "certification_eligible": True,
                "deprecated_endpoint": False,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    previous_manifest = _previous_manifest_for_temp_fixture(tmp_path, current, removed)

    inventory_1 = build_upstox_corpus_inventory(
        roots=[tmp_path / "dataset"],
        bundle_path=BUNDLE,
        previous_manifest_path=previous_manifest,
        code_commit="deadbeef",
    )
    inventory_2 = build_upstox_corpus_inventory(
        roots=[tmp_path / "dataset"],
        bundle_path=BUNDLE,
        previous_manifest_path=previous_manifest,
        code_commit="deadbeef",
    )

    assert inventory_1 == inventory_2
    assert any("20260716" in path for path in inventory_1["diff"]["files_added"])
    assert any("20260715" in path for path in inventory_1["diff"]["files_removed"])
    assert any(item["classification"] == "REPAIRED_PREVIOUS_FAILURE" for item in inventory_1["diff"]["files_changed"])
    assert any(item["file_role"] == "CACHE_ARTIFACT" and not item["accepted_for_snapshot"] for item in inventory_1["source_files"])
    zero_byte = next(item for item in inventory_1["source_files"] if item["logical_path"].endswith("ticks_20260705.jsonl"))
    assert zero_byte["file_role"] == "CACHE_ARTIFACT"
    assert zero_byte["accepted_for_snapshot"] is False
    assert zero_byte["inspection_error"] == "cache_artifact"
    assert sum(1 for _ in {item["sha256"] for item in inventory_1["source_files"]}) < sum(1 for _ in inventory_1["source_files"])
    assert any(item["file_role"] == "FETCH_MANIFEST" and item["reconciliation_status"] == "FETCH_SUCCESS_RECONCILED" for item in inventory_1["source_files"])
    assert any(item["data_role"] == "OPTION_DEPTH" for item in inventory_1["source_files"])

    out_inventory = tmp_path / "inventory.json"
    out_manifest = tmp_path / "manifest.json"
    inv_path, inv_sidecar = write_inventory_and_sidecar(inventory_1, output_path=out_inventory)
    inv_path_2, inv_sidecar_2 = write_inventory_and_sidecar(inventory_2, output_path=tmp_path / "inventory-2.json")
    man = build_four_strategy_dataset_manifest_v2(
        roots=[tmp_path / "dataset"],
        bundle_path=BUNDLE,
        previous_manifest_path=previous_manifest,
        inventory=inventory_1,
        code_commit="deadbeef",
    )
    man_path, man_sidecar = write_v2_manifest_and_sidecar(man, output_path=out_manifest)
    man_path_2, man_sidecar_2 = write_v2_manifest_and_sidecar(man, output_path=tmp_path / "manifest-2.json")
    assert inv_path.exists()
    assert inv_sidecar.exists()
    assert inv_path_2.exists()
    assert inv_sidecar_2.exists()
    assert man_path.exists()
    assert man_sidecar.exists()
    assert man_path_2.exists()
    assert man_sidecar_2.exists()
    assert inv_path.read_bytes() == inv_path_2.read_bytes()
    assert man_path.read_bytes() == man_path_2.read_bytes()
    assert inv_sidecar.read_text(encoding="utf-8").split()[0] == inv_sidecar_2.read_text(encoding="utf-8").split()[0]
    assert man_sidecar.read_text(encoding="utf-8").split()[0] == man_sidecar_2.read_text(encoding="utf-8").split()[0]
    assert inv_sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(inv_path.read_bytes()).hexdigest()
    assert man_sidecar.read_text(encoding="utf-8").split()[0] == hashlib.sha256(man_path.read_bytes()).hexdigest()
    assert inv_path.stat().st_size < 20 * 1024 * 1024
    assert man_path.stat().st_size < 20 * 1024 * 1024

    compact_inventory = json.loads(inv_path.read_text(encoding="utf-8"))
    compact_manifest = json.loads(man_path.read_text(encoding="utf-8"))
    file_ids = set(compact_inventory["files"])
    family_ids = set(compact_inventory["families"])
    assert {"files", "families", "composites", "joinability_summary", "duplicate_content_summary"} <= set(compact_inventory)
    assert {"inventory_summary", "strategy_summary", "composite_corpora", "composite_generation_policy"} <= set(compact_manifest)
    assert sum(item["file_count"] for item in compact_inventory["source_root_authority"]) == compact_inventory["file_counts"]["total_source_files"]
    assert compact_inventory["file_counts"]["total_source_files"] - compact_inventory["file_counts"]["unique_file_hashes"] == compact_inventory["duplicate_content_counts"]["duplicate_file_count"]
    assert compact_inventory["duplicate_content_counts"]["duplicate_content_group_count"] == sum(
        1 for _ in compact_inventory["duplicate_content_summary"]["duplicate_groups"]
    )
    assert all("schema_columns" not in item for item in compact_inventory["files"].values())
    assert all(set(item["component_file_ids"]).issubset(file_ids) for item in compact_inventory["families"].values())
    assert all(set(item["component_family_ids"]).issubset(family_ids) for item in compact_inventory["composites"].values())
    assert all(set(item["component_family_ids"]).issubset(family_ids) for item in compact_manifest["composite_corpora"])
    assert compact_manifest["inventory_summary"]["dataset_family_count"] == len(compact_inventory["families"])
    assert compact_manifest["inventory_summary"]["composite_corpus_count"] == len(compact_inventory["composites"])
    assert set(compact_manifest["composite_generation_policy"]["representative_accepted_composites"]).issubset(set(compact_inventory["composites"]))
    assert set(compact_manifest["composite_generation_policy"]["representative_rejected_composites"]).issubset(set(compact_inventory["composites"]))


def test_live_inventory_separates_signal_and_execution_suitability(live_inventory: dict[str, object], live_manifest: dict[str, object]) -> None:
    assert live_inventory["requested_source_roots"] == [str(path) for path in ROOTS]
    assert sum(1 for _ in live_inventory["source_root_authority"]) == 2
    assert {item["root_status"] for item in live_inventory["source_root_authority"]} == {"AVAILABLE_WITH_DATA"}
    assert all(item["requested_path"] in {str(path) for path in ROOTS} for item in live_inventory["source_root_authority"])
    assert all(item["resolved_path"] for item in live_inventory["source_root_authority"])
    assert live_inventory["file_counts"]["manifest_files"] >= 663
    assert live_inventory["coverage"]["nifty"]["session_count"] == 521
    assert live_inventory["coverage"]["banknifty"]["session_count"] == 501
    assert live_inventory["coverage"]["other_underlyings"]["symbols"] == ["SENSEX"]
    assert live_inventory["coverage"]["other_underlyings"]["session_count"] >= 1
    assert live_inventory["coverage"]["option_history"]["option_ltp_session_count"] > 0
    assert live_inventory["coverage"]["option_history"]["option_quote_session_count"] == 0
    assert live_inventory["coverage"]["option_history"]["option_depth_session_count"] > 0
    assert any("20260716" in path for path in live_inventory["diff"]["files_added"])
    assert live_inventory["reconciliation"]["by_status"]["FETCH_SUCCESS_RECONCILED"] >= 1

    assert live_manifest["signal_verdict"] in {
        "COMPOSITE_SIGNAL_DATA_READY_WITH_PROVENANCE_LIMITATIONS",
        "PARTIAL_COMPOSITE_SIGNAL_COVERAGE",
    }
    assert live_manifest["execution_verdict"] in {
        "PARTIAL_EXECUTION_DATA_COVERAGE",
        "EXECUTION_DATA_BLOCKED",
    }
    assert live_manifest["corpus_status"] == "PARTIAL"
    assert live_manifest["inventory_summary"]["dataset_family_count"] > 0
    assert live_manifest["inventory_summary"]["composite_corpus_count"] > 0
    strategies = {item["strategy_id"]: item for item in live_manifest["strategy_summary"]}
    assert set(strategies) == {
        "opening_range_retest_v1",
        "compression_breakout_v1",
        "trend_pullback_v1",
        "vwap_reclaim_rejection_v1",
    }
    assert all("signal_suitability" in item and "execution_suitability" in item for item in strategies.values())


def test_missing_explicit_root_fails_closed(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError):
        build_upstox_corpus_inventory(
            roots=[missing],
            bundle_path=BUNDLE,
            previous_manifest_path=V1_MANIFEST,
            code_commit="deadbeef",
        )


def test_cli_requires_explicit_input_roots() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "build_four_strategy_dataset_manifest.py"),
            "--contract-bundle",
            str(BUNDLE),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--input" in result.stderr
