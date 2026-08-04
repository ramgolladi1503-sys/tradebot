from __future__ import annotations

import pandas as pd

from core.analytics.candidate_ml_v2.corpus_loader import load_market_tick_corpus_resilient


def test_resilient_loader_quarantines_incompatible_shard(tmp_path):
    incompatible = tmp_path / "resolved_rows.parquet"
    pd.DataFrame(
        {
            "instrument_key": ["NSE_FO|1"],
            "ltp": [100.0],
            "resolution": ["TARGET"],
        }
    ).to_parquet(incompatible, index=False)

    compatible = tmp_path / "ticks.parquet"
    pd.DataFrame(
        {
            "ts_epoch_ms": [1_700_000_000_000, 1_700_000_060_000],
            "instrument": ["NSE_INDEX|Nifty 50", "NSE_FO|1"],
            "last_price": [20_000.0, 100.0],
            "bid": [None, 99.9],
            "ask": [None, 100.1],
        }
    ).to_parquet(compatible, index=False)

    frame, manifest = load_market_tick_corpus_resilient([incompatible, compatible])

    assert frame.shape[0] == 2
    assert manifest["source_file_count"] == 1
    assert manifest["rejected_file_count"] == 1
    assert manifest["rejected_files"][0]["path"].endswith("resolved_rows.parquet")
    assert "timestamp_column_missing" in manifest["rejected_files"][0]["reason"]
    assert manifest["allowed_for_live_execution"] is False
    assert manifest["broker_api_called"] is False
