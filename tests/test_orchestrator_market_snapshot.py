from __future__ import annotations

import core.orchestrator as orch_mod


def test_produce_and_store_market_snapshot_writes_expected_structure(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        orch_mod,
        "write_market_snapshot_atomic",
        lambda snapshot: captured.setdefault("snapshot", snapshot),
    )

    snapshot = orch_mod.produce_and_store_market_snapshot(
        market_data_list=[
            {
                "symbol": "NIFTY",
                "market_open": True,
                "ltp": 22510.0,
                "quote_age_sec": 0.5,
                "regime": "TREND_DAY",
                "primary_regime": "TREND_DAY",
                "regime_confidence": 0.72,
                "day_type": "NORMAL",
                "cross_asset_quality": {"status": "OK", "any_stale": False},
                "option_chain_health": {"status": "OK", "quote_age_sec": 0.8},
                "option_chain": [{"strike": 22500.0}, {"strike": 22550.0}],
            }
        ],
        market_open=True,
        compute_ms=12.5,
        loop_id="loop-42",
    )

    assert captured["snapshot"] == snapshot
    assert snapshot["source"] == "engine"
    assert snapshot["market_open"] is True
    assert snapshot["producer_meta"]["loop_id"] == "loop-42"
    assert snapshot["symbols"]["NIFTY"]["ltp"] == 22510.0
    assert snapshot["symbols"]["NIFTY"]["cross_asset"]["available"] is True
