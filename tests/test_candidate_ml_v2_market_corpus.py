from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.analytics import candidate_ml_v2 as mod


def _tick_frame(*, sessions: int = 6, minutes: int = 40, option_count: int = 12) -> pd.DataFrame:
    rows: list[dict] = []
    base = pd.Timestamp("2026-07-14 03:45:00", tz="UTC")
    for day in range(sessions):
        for minute in range(minutes):
            timestamp = base + pd.Timedelta(days=day, minutes=minute)
            direction = 1.0 if day % 2 == 0 else -1.0
            index_price = 25_000.0 + day * 20.0 + direction * minute * 2.0
            rows.append(
                {
                    "timestamp": timestamp,
                    "instrument_key": "NSE_INDEX|Nifty 50",
                    "ltp": index_price,
                    "bid_price": np.nan,
                    "ask_price": np.nan,
                    "volume": 1_000.0 + minute,
                    "oi": np.nan,
                    "iv": np.nan,
                    "delta": np.nan,
                    "theta": np.nan,
                    "gamma": np.nan,
                    "vega": np.nan,
                    "source_file": "synthetic_test_only",
                }
            )
            for option_index in range(option_count):
                option_direction = direction if option_index % 3 else -direction
                option_price = 100.0 + option_index + option_direction * minute * 0.15
                rows.append(
                    {
                        "timestamp": timestamp + pd.Timedelta(seconds=option_index % 10),
                        "instrument_key": f"NSE_FO|{1000 + option_index}",
                        "ltp": option_price,
                        "bid_price": option_price - 0.10,
                        "ask_price": option_price + 0.10,
                        "volume": 100.0 + option_index + minute,
                        "oi": 1_000.0 + option_index,
                        "iv": 15.0 + option_index * 0.1,
                        "delta": option_index * 0.05,
                        "theta": -option_index * 0.01,
                        "gamma": option_index * 0.001,
                        "vega": option_index * 0.02,
                        "source_file": "synthetic_test_only",
                    }
                )
    return pd.DataFrame(rows)


def test_market_corpus_audit_and_pretraining_dataset_are_causal():
    source = _tick_frame()
    config = mod.MarketCorpusConfig(
        horizon_bars=5,
        min_move_bps=0.10,
        min_option_instruments_per_bar=10,
    )
    audit = mod.audit_market_tick_corpus(source, config)
    assert audit["verdict"] == "REAL_MARKET_CORPUS_AVAILABLE"
    assert audit["sessions"] == 6
    assert audit["candidate_lineage_available"] is False
    assert audit["allowed_for_live_execution"] is False

    dataset = mod.build_market_response_pretraining_dataset(source, config)
    assert dataset.shape[0] == 420
    assert dataset["session_date"].nunique() == 6
    assert set(dataset["strategy_id"].unique()) == {"MARKET_RESPONSE_LONG", "MARKET_RESPONSE_SHORT"}
    assert dataset["target"].nunique() == 2
    assert (dataset["feature_cutoff_ts_epoch_ms"] <= dataset["decision_ts_epoch_ms"]).all()
    assert (dataset["outcome_ts_epoch_ms"] > dataset["decision_ts_epoch_ms"]).all()
    assert dataset["broker_api_called"].eq(False).all()
    assert dataset["is_order_action"].eq(False).all()


def test_market_state_rejects_missing_option_support():
    source = _tick_frame(option_count=2)
    with pytest.raises(ValueError, match="option_support_below_minimum"):
        mod.build_market_state_frame(
            source,
            mod.MarketCorpusConfig(min_option_instruments_per_bar=10),
        )


def test_materialized_parquet_guard_rejects_lfs_pointer(tmp_path):
    pointer = tmp_path / "ticks.parquet"
    pointer.write_text(
        "version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 123\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="lfs_pointer_not_materialized"):
        mod.validate_materialized_parquet(pointer)

    parquet_header = tmp_path / "materialized.parquet"
    parquet_header.write_bytes(b"PAR1test")
    assert mod.validate_materialized_parquet(parquet_header) == parquet_header
