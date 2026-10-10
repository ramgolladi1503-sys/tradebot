"""Focused behavior tests for option contract identity and expiry-aware resolution.

Tests prove:
1. Same strike and option type across two expiries do not collide.
2. Querying with an exact expiry resolves exclusively the intended contract.
3. Missing expiry fails closed (returns None).
4. Ambiguous duplicate symbols fail closed (returns None).
5. Empty or missing matches fail closed (returns None).
"""

import pandas as pd
import pytest

from scripts.run_live_feed_advisor import SentinelLiveFeedAdvisor


@pytest.fixture
def mock_advisor(monkeypatch):
    """Instantiates SentinelLiveFeedAdvisor bypassing model manifest verification for unit tests."""
    monkeypatch.setattr(
        "core.model_manifest_generator.SentinelManifestLock.verify_manifest_or_fail_closed",
        lambda self: True,
    )
    # Provide a minimal mock calibration file path if needed
    monkeypatch.setattr(
        "builtins.open",
        lambda f, *args, **kwargs: (
            open(__file__, "r") if "calibrated_regime_matrix" not in str(f)
            else type("MockFile", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None, "read": lambda s: "{}"})()
        ),
    )
    monkeypatch.setattr("json.load", lambda f: {})
    advisor = SentinelLiveFeedAdvisor(artifacts_dir="artifacts", ticker="NIFTY")
    return advisor


def test_missing_expiry_fails_closed(mock_advisor):
    """Proves that querying without an explicit expiry returns None."""
    df = pd.DataFrame([
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|44598",
            "symbol": "NIFTY 22300 CE 13 OCT 26",
            "ltp": 180.75,
            "bid": 180.95,
            "ask": 181.50,
            "vol": 1000.0,
            "oi": 50000.0,
        }
    ])
    
    # Neither instance target_expiry nor argument expiry provided
    mock_advisor.target_expiry = None
    res = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry=None)
    assert res is None, "Missing expiry must fail closed"
    
    res_empty = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry="   ")
    assert res_empty is None, "Whitespace expiry must fail closed"


def test_cross_expiry_collision_prevention(mock_advisor):
    """Proves that identical strike/type across two distinct expiries cannot collide."""
    df = pd.DataFrame([
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|44598",
            "symbol": "NIFTY 22300 CE 13 OCT 26",
            "ltp": 180.75,
            "bid": 180.95,
            "ask": 181.50,
            "vol": 1000.0,
            "oi": 50000.0,
        },
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|44605",
            "symbol": "NIFTY 22300 CE 20 OCT 26",
            "ltp": 210.50,
            "bid": 210.00,
            "ask": 211.00,
            "vol": 500.0,
            "oi": 20000.0,
        },
    ])

    # Querying 13 OCT 26 must resolve Token 44598 exclusively
    res_oct13 = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry="13 OCT 26")
    assert res_oct13 is not None
    assert res_oct13["token"] == "NSE_FO|44598"
    assert res_oct13["symbol"] == "NIFTY 22300 CE 13 OCT 26"
    assert res_oct13["ltp"] == 180.75

    # Querying 20 OCT 26 must resolve Token 44605 exclusively
    res_oct20 = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry="20 OCT 26")
    assert res_oct20 is not None
    assert res_oct20["token"] == "NSE_FO|44605"
    assert res_oct20["symbol"] == "NIFTY 22300 CE 20 OCT 26"
    assert res_oct20["ltp"] == 210.50

    # Querying non-existent expiry 27 OCT 26 must return None
    res_oct27 = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry="27 OCT 26")
    assert res_oct27 is None


def test_ambiguous_multiple_matches_fail_closed(mock_advisor):
    """Proves that multiple ambiguous contracts matching the criteria fail closed."""
    df = pd.DataFrame([
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|11111",
            "symbol": "NIFTY 22300 CE 13 OCT 26 W1",
            "ltp": 180.0,
            "bid": 179.0,
            "ask": 181.0,
            "vol": 100.0,
            "oi": 1000.0,
        },
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|22222",
            "symbol": "NIFTY 22300 CE 13 OCT 26 W2",
            "ltp": 182.0,
            "bid": 181.0,
            "ask": 183.0,
            "vol": 200.0,
            "oi": 2000.0,
        },
    ])

    res = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE", expiry="13 OCT 26")
    assert res is None, "Ambiguous multiple contract symbols matching same expiry must fail closed"


def test_instance_target_expiry_propagation(mock_advisor):
    """Proves that advisor instance target_expiry propagates when argument expiry is omitted."""
    df = pd.DataFrame([
        {
            "ts": 1728445800.0,
            "token": "NSE_FO|44598",
            "symbol": "NIFTY 22300 CE 13 OCT 26",
            "ltp": 180.75,
            "bid": 180.95,
            "ask": 181.50,
            "vol": 1000.0,
            "oi": 50000.0,
        }
    ])

    mock_advisor.target_expiry = "13 OCT 26"
    res = mock_advisor.resolve_quote_from_dataframe(df, strike=22300, opt_type="CE")
    assert res is not None
    assert res["token"] == "NSE_FO|44598"
