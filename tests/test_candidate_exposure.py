from core.candidate_exposure import (
    EXPOSURE_BEARISH,
    EXPOSURE_BULLISH,
    EXPOSURE_RANGE,
    EXPOSURE_UNKNOWN,
    SETUP_DIRECTIONAL,
    SETUP_RANGE_COMPATIBLE,
    SETUP_UNKNOWN,
    normalize_directional_exposure,
)


def test_directional_exposure_uses_direction_and_option_type():
    bullish = normalize_directional_exposure({"direction": "BUY_CALL", "option_type": "CE"})
    bearish = normalize_directional_exposure({"direction": "BUY_PUT", "option_type": "PE"})

    assert bullish.exposure == EXPOSURE_BULLISH
    assert bearish.exposure == EXPOSURE_BEARISH
    assert bullish.setup_kind == SETUP_UNKNOWN
    assert bearish.setup_kind == SETUP_UNKNOWN


def test_directional_exposure_infers_range_from_family_movement_and_regime():
    exposure = normalize_directional_exposure(
        {
            "direction": "BUY_CALL",
            "strategy_family": "mean_reversion",
            "movement_type": "MEAN_REVERSION_EXTENSION",
            "regime": "RANGE",
        }
    )

    assert exposure.exposure == EXPOSURE_RANGE
    assert exposure.setup_kind == SETUP_RANGE_COMPATIBLE
    assert "setup_range_compatible" in exposure.evidence


def test_directional_exposure_can_use_signal_direction():
    exposure = normalize_directional_exposure({"signal_direction": "BUY_PUT"})

    assert exposure.exposure == EXPOSURE_BEARISH
    assert "signal_bearish" in exposure.evidence


def test_unknown_exposure_stays_conservative():
    exposure = normalize_directional_exposure({"symbol": "NIFTY"})

    assert exposure.exposure == EXPOSURE_UNKNOWN
    assert exposure.setup_kind == "UNKNOWN"
