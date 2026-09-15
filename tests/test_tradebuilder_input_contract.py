"""Unit tests for TradeBuilder authoritative input contract."""

from __future__ import annotations

import pytest

from core.trade_truth.trade_builder_input_contract import (
    build_canonical_tradebuilder_input,
    hash_tradebuilder_input,
)


def test_build_canonical_tradebuilder_input_valid():
    inp = build_canonical_tradebuilder_input(
        symbol="NIFTY",
        ltp=24500.5,
        regime={"primary_regime": "TRENDING"},
        cycle_id="s1:1:c1",
        session_id="s1",
        source_sha="a" * 40,
        market_open=True,
        execution_mode="PAPER",
    )
    assert inp["symbol"] == "NIFTY"
    assert inp["ltp"] == 24500.5
    assert inp["close"] == 24500.5
    assert inp["regime"]["primary_regime"] == "TRENDING"
    assert inp["cycle_id"] == "s1:1:c1"
    assert inp["read_only"] is True
    assert inp["is_order_action"] is False
    assert inp["broker_write_authority"] is False
    assert inp["order_authority"] is False
    assert inp["market_open"] is True
    assert inp["execution_mode"] == "PAPER"


@pytest.mark.parametrize("missing_symbol", ["", None, "   "])
def test_build_canonical_input_missing_symbol_fails_closed(missing_symbol):
    with pytest.raises(ValueError, match="TRADEBUILDER_INPUT_MISSING_SYMBOL"):
        build_canonical_tradebuilder_input(
            symbol=missing_symbol,
            ltp=24500.0,
            regime={"primary_regime": "TRENDING"},
            cycle_id="c1",
            session_id="s1",
            source_sha="a" * 40,
        )


@pytest.mark.parametrize("invalid_ltp", [0.0, -10.5, None, "invalid"])
def test_build_canonical_input_non_positive_ltp_fails_closed(invalid_ltp):
    with pytest.raises(ValueError, match="TRADEBUILDER_INPUT_"):
        build_canonical_tradebuilder_input(
            symbol="NIFTY",
            ltp=invalid_ltp,
            regime={"primary_regime": "TRENDING"},
            cycle_id="c1",
            session_id="s1",
            source_sha="a" * 40,
        )


@pytest.mark.parametrize("missing_regime", [{}, None, "not_a_map"])
def test_build_canonical_input_missing_regime_fails_closed(missing_regime):
    with pytest.raises(ValueError, match="TRADEBUILDER_INPUT_MISSING_REGIME"):
        build_canonical_tradebuilder_input(
            symbol="NIFTY",
            ltp=24500.0,
            regime=missing_regime,
            cycle_id="c1",
            session_id="s1",
            source_sha="a" * 40,
        )


def test_hash_tradebuilder_input_deterministic():
    payload1 = {
        "symbol": "NIFTY",
        "ltp": 24500.0,
        "regime": {"primary_regime": "TRENDING"},
        "cycle_id": "c1",
    }
    payload2 = {
        "cycle_id": "c1",
        "regime": {"primary_regime": "TRENDING"},
        "ltp": 24500.0,
        "symbol": "NIFTY",
    }
    h1 = hash_tradebuilder_input(payload1)
    h2 = hash_tradebuilder_input(payload2)
    assert h1 == h2
    assert len(h1) == 64
