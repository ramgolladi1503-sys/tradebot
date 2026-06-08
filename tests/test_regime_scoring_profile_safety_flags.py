from core.movement_regime import MovementRegimeResult
from core.regime_scoring_profiles import resolve_regime_scoring_profile


def test_regime_profile_serializes_read_only_non_broker_flags():
    regime = MovementRegimeResult(
        schema_version=1,
        primary_regime="TREND_UP",
        scores={
            "TREND_UP": 0.9,
            "TREND_DOWN": 0.0,
            "RANGE": 0.0,
            "CHOP": 0.0,
            "COMPRESSION": 0.0,
            "VOLATILITY_EXPANSION": 0.0,
            "TRAP_RISK": 0.0,
            "EXHAUSTION_RISK": 0.0,
            "EXPIRY_CONTEXT": 0.0,
            "INCONCLUSIVE": 0.0,
        },
    )

    payload = resolve_regime_scoring_profile(regime).to_dict()

    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False
