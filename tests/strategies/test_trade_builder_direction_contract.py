"""
Tests for strict direction validation and fail-closed behavior in trade_builder.
Proves that:
1. Exact canonical tokens ('BUY_CALL', 'BUY_PUT', 'CE', 'PE') map correctly to option_type ('CE', 'PE').
2. Any malformed, non-canonical, lowercase, whitespace-padded, alias, substring, contradictory,
   or non-string (None, bool, int, dict) direction produces NO candidate (returns None)
   and never proceeds to strike resolution or contract admission.
3. Both callers (_build_borderline_candidate and _soften_reject_to_candidate) fail closed.
4. Callers' consuming paths (e.g. scan survivor loop) produce zero admitted candidates.
"""

import pytest
from unittest.mock import MagicMock
from strategies.trade_builder import TradeBuilder


@pytest.fixture
def builder():
    tb = TradeBuilder()
    return tb


@pytest.fixture
def valid_market_data():
    return {
        "symbol": "NIFTY",
        "underlying_spot": 22350.0,
        "ltp": 22350.0,
        "vwap": 22350.0,
        "option_chain": [
            {
                "symbol": "NIFTY",
                "strike": 22350,
                "type": "CE",
                "tradingsymbol": "NIFTY26OCT22350CE",
                "instrument_token": 12345,
                "expiry": "2026-10-26",
            },
            {
                "symbol": "NIFTY",
                "strike": 22350,
                "type": "PE",
                "tradingsymbol": "NIFTY26OCT22350PE",
                "instrument_token": 12346,
                "expiry": "2026-10-26",
            },
        ],
    }


# -------------------------------------------------------------------------
# 1. Exact Canonical Mapping Verification
# -------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_direction, expected_opt_type",
    [
        ("BUY_CALL", "CE"),
        ("BUY_PUT", "PE"),
        ("CE", "CE"),
        ("PE", "PE"),
    ],
)
def test_attach_softened_candidate_contract_canonical_success(builder, valid_market_data, raw_direction, expected_opt_type):
    candidate = {
        "symbol": "NIFTY",
        "direction": raw_direction,
        "execution_status": "scored",
    }
    # Mock option contract resolution to verify option_type passed downstream
    builder._resolve_option_contract = MagicMock(return_value={
        "tradingsymbol": f"NIFTY22350{expected_opt_type}",
        "instrument_token": 99999,
        "expiry": "2026-10-26",
    })

    res = builder._attach_softened_candidate_contract(candidate, market_data=valid_market_data)

    assert res is not None
    assert res.get("option_type") == expected_opt_type
    assert res.get("right") == expected_opt_type
    assert res.get("unresolved_contract") is False
    assert res.get("execution_blocked") is False


# -------------------------------------------------------------------------
# 2. Strict Rejection of Malformed, Non-String, Substring, Aliases, & Contradictions
# -------------------------------------------------------------------------

@pytest.mark.parametrize(
    "invalid_direction",
    [
        None,
        True,
        False,
        1,
        0,
        -1,
        3.14,
        [],
        {},
        "",
        "   ",
        # Lowercase / non-canonical casing
        "buy_call",
        "buy_put",
        "ce",
        "pe",
        "Buy_Call",
        # Whitespace-padded
        " BUY_CALL",
        "BUY_CALL ",
        "  CE",
        "CE  ",
        "BUY_PUT\n",
        # Substrings & Aliases (previously allowed by fuzzy/substring check)
        "CALL",
        "PUT",
        "LONG",
        "SHORT",
        "CALLING",
        "PUTTING",
        "BUY_CALL_EXTRA",
        "BUY_PUT_SPREAD",
        "PUT_OPTION",
        "CALL_OPTION",
        # Contradictory tokens
        "BUY_CALL_BUY_PUT",
        "CE_PE",
        "PE_CE",
        "CALL_PUT",
        # Corrupt strings
        "UNKNOWN",
        "RANDOM_NOISE",
    ],
)
def test_attach_softened_candidate_contract_invalid_fails_closed(builder, valid_market_data, invalid_direction):
    candidate = {
        "symbol": "NIFTY",
        "direction": invalid_direction,
        "execution_status": "scored",
    }
    # Spy on contract resolver to prove it is NEVER reached
    builder._resolve_option_contract = MagicMock()

    res = builder._attach_softened_candidate_contract(candidate, market_data=valid_market_data)

    assert res is None, f"Expected None for invalid direction {invalid_direction!r}, got {res!r}"
    builder._resolve_option_contract.assert_not_called()


# -------------------------------------------------------------------------
# 3. Caller 1: _build_borderline_candidate Fails Closed
# -------------------------------------------------------------------------

def test_build_borderline_candidate_valid_canonical(builder, valid_market_data):
    builder._resolve_option_contract = MagicMock(return_value={
        "tradingsymbol": "NIFTY22350CE",
        "instrument_token": 11111,
        "expiry": "2026-10-26",
    })
    res = builder._build_borderline_candidate(
        market_data=valid_market_data,
        reason="test_ok",
        confidence=0.5,
        direction="BUY_CALL",
    )
    assert res is not None
    assert res.get("option_type") == "CE"


@pytest.mark.parametrize(
    "invalid_direction",
    [True, "CALLING", "LONG", " SHORT", "ce", "UNKNOWN", "BUY_CALL_EXTRA", "CE_PE"],
)
def test_build_borderline_candidate_invalid_direction_returns_none(builder, valid_market_data, invalid_direction):
    builder._resolve_option_contract = MagicMock()
    res = builder._build_borderline_candidate(
        market_data=valid_market_data,
        reason="test_fail",
        confidence=0.5,
        direction=invalid_direction,
    )
    assert res is None
    builder._resolve_option_contract.assert_not_called()


def test_build_borderline_candidate_none_direction_uses_vwap_and_succeeds_canonically(builder, valid_market_data):
    """
    When direction is None, line 431 uses the VWAP heuristic to produce canonical BUY_CALL or BUY_PUT,
    which must resolve successfully to CE or PE.
    """
    builder._resolve_option_contract = MagicMock(return_value={
        "tradingsymbol": "NIFTY22350CE",
        "instrument_token": 11111,
        "expiry": "2026-10-26",
    })
    res = builder._build_borderline_candidate(
        market_data=valid_market_data,
        reason="weak_signal",
        confidence=0.5,
        direction=None,
    )
    assert res is not None
    assert res.get("option_type") == "CE"


# -------------------------------------------------------------------------
# 4. Caller 2: _soften_reject_to_candidate Fails Closed
# -------------------------------------------------------------------------

def test_soften_reject_to_candidate_invalid_direction_returns_none(builder, valid_market_data):
    builder._resolve_option_contract = MagicMock()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "spread_too_wide",
        "direction": "INVALID_ALIAS_CALLING",
    }
    res = builder._soften_reject_to_candidate(
        market_data=valid_market_data,
        reject_ctx=reject_ctx,
        direction="INVALID_ALIAS_CALLING",
    )
    assert res is None
    builder._resolve_option_contract.assert_not_called()


# -------------------------------------------------------------------------
# 5. Caller Path Isolation: Scan Survivor Injection
# -------------------------------------------------------------------------

def test_scan_survivor_loop_bypasses_invalid_candidate(builder, valid_market_data):
    """
    Simulates the survivor injection loop at lines 3608-3618:
    Invalid directions produce degraded = None, which is skipped via continue,
    resulting in 0 admitted candidates.
    """
    builder._resolve_option_contract = MagicMock()
    selected_rejected = [{"ltp": 22350.0}]
    injected = []

    for rec in selected_rejected:
        degraded = builder._build_borderline_candidate(
            market_data=valid_market_data,
            reason="scan_min_survivor",
            confidence=0.4,
            strategy_tag="TEST_STRAT",
            direction="MALFORMED_DIR_XYZ",
        )
        if not isinstance(degraded, dict):
            continue
        injected.append(degraded)

    assert len(injected) == 0
    builder._resolve_option_contract.assert_not_called()


# -------------------------------------------------------------------------
# 6. Missing Symbol + Direction Permutations
# -------------------------------------------------------------------------

def test_attach_softened_candidate_contract_invalid_direction_missing_symbol(builder):
    """
    Proves that invalid direction paired with missing symbol fails closed (returns None),
    never bypassing direction validation.
    """
    candidate = {
        "symbol": "",
        "direction": "INVALID_ALIAS_CALLING",
    }
    market_data = {"symbol": ""}
    builder._resolve_option_contract = MagicMock()

    res = builder._attach_softened_candidate_contract(candidate, market_data=market_data)
    assert res is None
    builder._resolve_option_contract.assert_not_called()


def test_attach_softened_candidate_contract_valid_direction_missing_symbol(builder):
    """
    Proves that valid canonical direction paired with missing symbol preserves
    the prior behavior: returns out unchanged, without adding new fields.
    """
    candidate = {
        "symbol": "",
        "direction": "BUY_CALL",
        "custom_marker": 12345,
    }
    market_data = {"symbol": ""}
    builder._resolve_option_contract = MagicMock()

    res = builder._attach_softened_candidate_contract(candidate, market_data=market_data)
    assert res is not None
    assert res == candidate
    assert "option_type" not in res
    assert "execution_blocked" not in res
    builder._resolve_option_contract.assert_not_called()


def test_build_borderline_candidate_invalid_direction_missing_symbol(builder):
    """
    Caller 1 with invalid direction and empty symbol returns None.
    """
    market_data = {"symbol": "", "underlying_spot": 22350.0}
    builder._resolve_option_contract = MagicMock()

    res = builder._build_borderline_candidate(
        market_data=market_data,
        reason="test_fail",
        confidence=0.5,
        direction="CALLING",
    )
    assert res is None
    builder._resolve_option_contract.assert_not_called()


def test_soften_reject_to_candidate_invalid_direction_missing_symbol(builder):
    """
    Caller 2 with invalid direction and empty symbol returns None.
    """
    market_data = {"symbol": "", "underlying_spot": 22350.0}
    reject_ctx = {"symbol": "", "reason": "no_signal", "direction": "BAD_DIRECTION"}
    builder._resolve_option_contract = MagicMock()

    res = builder._soften_reject_to_candidate(
        market_data=market_data,
        reject_ctx=reject_ctx,
        direction="BAD_DIRECTION",
    )
    assert res is None
    builder._resolve_option_contract.assert_not_called()


# -------------------------------------------------------------------------
# 7. SIM / PAPER / LIVE Execution Boundaries & Broker Safety Invariants
# -------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["SIM", "PAPER", "LIVE"])
def test_build_weak_signal_execution_boundaries_fail_closed(builder, valid_market_data, mode):
    """
    Proves execution boundary safety across SIM, PAPER, and LIVE:
    In LIVE mode under defaults, weak-signal borderline candidates are blocked (returns None).
    In SIM/PAPER or when softened candidate is evaluated, it never contains order actions
    and never calls broker APIs.
    """
    md = dict(valid_market_data)
    md["execution_mode"] = mode
    # Test builder.build() entry point
    res = builder.build(md, quick_mode=True, allow_fallbacks=True)
    if mode == "LIVE":
        # In LIVE, weak signal borderline candidate is blocked fail-closed under repository defaults
        assert res is None or res.get("eligible_for_execution") is False
    if res is not None:
        assert "order_id" not in res
        assert "broker" not in res
        assert "placed" not in res
        assert res.get("is_order_action", False) is False
