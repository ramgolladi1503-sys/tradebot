from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.ce_pe_replay_normalization_v1.build_readiness import (
    build,
)


def _write_fixture(snapshot: Path) -> Path:
    snapshot.mkdir()
    candidates = snapshot / "candidates"
    candidates.mkdir()
    master = candidates / "master.json"
    master.write_text(
        json.dumps(
            [
                {
                    "instrument_key": "CE1",
                    "instrument_type": "CE",
                    "strike_price": 25000,
                    "expiry": int(pd.Timestamp(date(2026, 7, 30)).timestamp() * 1000),
                    "trading_symbol": "BANKNIFTY26JUL25000CE",
                    "underlying_symbol": "BANKNIFTY",
                },
                {
                    "instrument_key": "PE1",
                    "instrument_type": "PE",
                    "strike_price": 25000,
                    "expiry": int(pd.Timestamp(date(2026, 7, 30)).timestamp() * 1000),
                    "trading_symbol": "BANKNIFTY26JUL25000PE",
                    "underlying_symbol": "BANKNIFTY",
                },
            ]
        )
    )
    raw = candidates / "ticks.parquet"
    pd.DataFrame(
        {
            "ts": [1784000700, 1784000760, 1784000700, 1784000760],
            "instrument_key": ["CE1", "CE1", "PE1", "PE1"],
            "ltp": [10.0, 10.2, 11.0, 11.1],
            "bid_price": [9.9, 10.1, 10.9, 11.0],
            "ask_price": [10.1, 10.3, 11.1, 11.2],
            "volume": [1, 2, 1, 2],
            "oi": [100, 101, 200, 201],
        }
    ).to_parquet(raw)
    from research.option_e2e_recertification_v4.current_certification_source_universe_v1.contract import sha256_file

    manifest = {
        "selected_candidates": [
            {
                "classification": "INSTRUMENT_MASTER",
                "snapshot_relative_path": "candidates/master.json",
                "physical_sha256": sha256_file(master),
                "candidate_id": "TEST:master.json",
            },
            {
                "classification": "REAL_OPTION_DATASET",
                "snapshot_relative_path": "candidates/ticks.parquet",
                "physical_sha256": sha256_file(raw),
                "candidate_id": "TEST:runtime/market_data/upstox/ticks.parquet",
            },
        ]
    }
    manifest_path = snapshot / "source_snapshot_manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    return manifest_path


def test_replay_readiness_invokes_real_loader_and_blocks_one_session(tmp_path: Path) -> None:
    manifest = _write_fixture(tmp_path / "snapshot")
    result = build(
        snapshot_manifest=manifest,
        output_root=tmp_path / "normalized",
        evidence_dir=tmp_path / "evidence",
        max_contracts=2,
    )

    assert result["strict_loader_pass_count"] == 2
    assert result["chronological_coverage_verdict"] == "ONE_SESSION_SMOKE_ONLY"
    assert result["normalization_result"] == "NORMALIZER_SMOKE_PASS"
    assert result["replay_dataset_verdict"] == "INSUFFICIENT_REPLAY_COVERAGE"
    assert result["oracle_agreement"] == "AGREEMENT"
    assert result["strategy_development_authorized"] is False
