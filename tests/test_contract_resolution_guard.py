from datetime import date

from core.contract_resolution_guard import classify_contract_resolution


REQUEST = {
    "requested_symbol": "NIFTY",
    "requested_expiry": date(2026, 5, 7),
    "requested_strike": 22500.0,
    "requested_option_type": "CE",
}


def test_contract_resolution_blocks_unresolved_contract():
    result = classify_contract_resolution(**REQUEST, resolved=None)

    assert result["ok"] is False
    assert result["blocker"] == "CONTRACT_UNRESOLVED"


def test_contract_resolution_blocks_missing_token():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={"resolution_path": "exact_contract_match", "instrument_token": None},
    )

    assert result["ok"] is False
    assert result["blocker"] == "CONTRACT_TOKEN_MISSING"


def test_contract_resolution_allows_exact_match():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={
            "resolution_path": "exact_contract_match",
            "instrument_token": 123456,
            "tradingsymbol": "NIFTY26MAY22500CE",
        },
    )

    assert result["ok"] is True
    assert result["classification"] == "exact_contract_match"
    assert result["blocker"] is None


def test_contract_resolution_allows_safe_nearest_fallback_inside_guardrails():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={
            "resolution_path": "safe_nearest_contract_fallback",
            "instrument_token": 123456,
            "resolved_expiry": date(2026, 5, 8),
            "resolved_strike": 22550.0,
        },
        max_expiry_distance_days=2,
        max_strike_distance=75.0,
    )

    assert result["ok"] is True
    assert result["classification"] == "safe_nearest_contract_fallback"
    assert result["expiry_distance_days"] == 1
    assert result["strike_distance"] == 50.0


def test_contract_resolution_blocks_fallback_expiry_too_far():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={
            "resolution_path": "safe_nearest_contract_fallback",
            "instrument_token": 123456,
            "resolved_expiry": date(2026, 5, 15),
            "resolved_strike": 22500.0,
        },
        max_expiry_distance_days=2,
        max_strike_distance=75.0,
    )

    assert result["ok"] is False
    assert result["blocker"] == "FALLBACK_EXPIRY_DISTANCE_EXCEEDED"


def test_contract_resolution_blocks_fallback_strike_too_far():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={
            "resolution_path": "safe_nearest_contract_fallback",
            "instrument_token": 123456,
            "resolved_expiry": date(2026, 5, 8),
            "resolved_strike": 22700.0,
        },
        max_expiry_distance_days=2,
        max_strike_distance=75.0,
    )

    assert result["ok"] is False
    assert result["blocker"] == "FALLBACK_STRIKE_DISTANCE_EXCEEDED"


def test_contract_resolution_blocks_unknown_resolution_path():
    result = classify_contract_resolution(
        **REQUEST,
        resolved={
            "resolution_path": "unsafe_guess",
            "instrument_token": 123456,
        },
    )

    assert result["ok"] is False
    assert result["blocker"] == "CONTRACT_RESOLUTION_PATH_UNKNOWN"
