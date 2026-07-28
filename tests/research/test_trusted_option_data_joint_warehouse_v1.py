from __future__ import annotations

import pandas as pd

from research.trusted_option_data_joint_warehouse_v1.builder import classify_option_source, data_contract, parse_ts


def test_classification_blocks_missing_contract_identity(tmp_path):
    path = tmp_path / "option_ticks.parquet"
    frame = pd.DataFrame(
        {
            "exchange_timestamp": ["2026-07-02 10:00:00"],
            "symbol": ["NIFTY"],
            "instrument_token": [1],
            "last_price": [100.0],
            "best_bid": [99.5],
            "best_ask": [100.5],
            "volume": [1000],
        }
    )
    frame.to_parquet(path)
    row = classify_option_source(path, frame)
    assert row["classification"] == "OBSERVATIONAL_ONLY"
    assert row["suitable_for_causal_replay"] is False
    assert "missing_strike_expiry_option_type" in row["exclusion_reason"]


def test_classification_accepts_full_contract_identity(tmp_path):
    path = tmp_path / "option_contract.parquet"
    frame = pd.DataFrame(
        {
            "timestamp": ["2026-07-02 10:00:00"],
            "underlying": ["NIFTY"],
            "strike": [25000],
            "expiry": ["2026-07-09"],
            "option_type": ["CE"],
            "ltp": [100.0],
            "bid": [99.5],
            "ask": [100.5],
        }
    )
    frame.to_parquet(path)
    row = classify_option_source(path, frame)
    assert row["classification"] == "TRUSTED_RAW"
    assert row["suitable_for_causal_replay"] is True


def test_data_contract_requires_contract_identity():
    contract = data_contract()
    assert contract["required_contract_identity"] == ["underlying", "expiry_date", "strike", "option_type"]
    assert contract["ambiguous_source_policy"].startswith("excluded")
