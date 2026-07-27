from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from research.option_e2e_recertification_v4.contract_reconstruction_v4_1.analyze_contract_reconstruction import (
    build_coverage,
    write_artifacts,
)


def test_reconstructs_identity_but_blocks_without_point_in_time_authority(tmp_path: Path) -> None:
    repo = tmp_path
    master_dir = repo / "runtime" / "upstox_instruments"
    master_dir.mkdir(parents=True)
    (master_dir / "complete.json").write_text(
        json.dumps(
            [
                {
                    "underlying_symbol": "NIFTY",
                    "instrument_type": "CE",
                    "instrument_key": "NSE_FO|123",
                    "exchange_token": "123",
                    "expiry": 1783727999000,
                    "strike_price": 25000.0,
                    "trading_symbol": "NIFTY 25000 CE 10 JUL 26",
                }
            ]
        ),
        encoding="utf-8",
    )
    quote_dir = repo / "runtime" / "market_data" / "upstox" / "20260702"
    quote_dir.mkdir(parents=True)
    pd.DataFrame(
        {
            "ts": [1782970200.0],
            "instrument_key": ["NSE_FO|123"],
            "ltp": [101.0],
            "bid_price": [100.5],
            "ask_price": [101.5],
        }
    ).to_parquet(quote_dir / "ticks_1782970200.parquet")

    coverage, summary = build_coverage(repo, [quote_dir])

    assert summary["files_discovered"] == 1
    assert summary["files_with_reconstructed_identity"] == 1
    assert summary["files_proving_historical_contract_existence"] == 0
    assert coverage[0].has_nifty is True
    assert coverage[0].has_ce_pe is True
    assert coverage[0].has_strike is True
    assert coverage[0].has_expiry is True
    assert coverage[0].has_no_post_expiry_rows is True
    assert "NO_POINT_IN_TIME_INSTRUMENT_AUTHORITY" in coverage[0].blocker


def test_write_artifacts_includes_hash(tmp_path: Path) -> None:
    repo = tmp_path
    master_dir = repo / "runtime" / "upstox_instruments"
    master_dir.mkdir(parents=True)
    (master_dir / "complete.json").write_text("[]", encoding="utf-8")
    quote_dir = repo / "runtime" / "market_data" / "upstox"
    quote_dir.mkdir(parents=True)
    pd.DataFrame({"ts": [1782970200.0], "instrument_key": ["feeds"], "ltp": [1.0]}).to_parquet(
        quote_dir / "ticks_1782970200.parquet"
    )

    coverage, summary = build_coverage(repo, [quote_dir])
    output_dir = repo / "out"
    write_artifacts(coverage, summary, output_dir)

    assert (output_dir / "coverage_matrix.json").exists()
    digest_line = (output_dir / "coverage_matrix.json.sha256").read_text(encoding="utf-8")
    assert digest_line.endswith("  coverage_matrix.json\n")
