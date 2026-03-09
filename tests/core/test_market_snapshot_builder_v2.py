from __future__ import annotations

import pytest

from core.market_snapshot_builder import build_market_snapshot, build_symbol_market_snapshot


def test_build_symbol_market_snapshot_normalizes_missing_sections():
    payload = build_symbol_market_snapshot(spot=22500.0, regime={"trend": "TREND"})

    assert payload["spot"] == 22500.0
    assert payload["ohlc"] == {"open": None, "high": None, "low": None, "close": None}
    assert payload["regime"] == {
        "trend": "TREND",
        "volatility_state": None,
        "confidence": None,
    }
    assert payload["option_chain_summary"]["chain_quality"] is None


def test_build_market_snapshot_raises_when_compact_payload_invalid():
    with pytest.raises(ValueError, match="invalid_market_snapshot"):
        build_market_snapshot(
            generated_at="",
            market_open=True,
            symbols_payload={"NIFTY": {"spot": 22500.0}},
            warnings=[],
            compute_ms=None,
            loop_id=None,
        )
