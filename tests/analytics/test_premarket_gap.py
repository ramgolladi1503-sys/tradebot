from datetime import datetime, timedelta, timezone

import pytest

from core.analytics.premarket_gap import (
    EvidenceAuthority,
    GapClass,
    GapResponseState,
    PreMarketSnapshot,
    build_gap_prediction,
    measure_gap_response,
    score_gap_prediction,
)


def _snapshot(**overrides):
    cutoff = datetime(2026, 8, 21, 9, 8, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    values = dict(
        index="NIFTY",
        cutoff_ts=cutoff,
        previous_close=24231.85,
        gift_last=24326.0,
        gift_previous_settlement=24294.0,
        gift_ts=cutoff - timedelta(minutes=2),
        lower_uncertainty_points=12.0,
        upper_uncertainty_points=13.0,
    )
    values.update(overrides)
    return PreMarketSnapshot(**values)


def test_basis_corrected_prediction_does_not_compare_absolute_gift_to_cash():
    prediction = build_gap_prediction(_snapshot())

    assert prediction.status == "PREDICTED"
    assert prediction.previous_basis_points == pytest.approx(62.15)
    assert prediction.gift_gap_points == pytest.approx(32.0)
    assert prediction.central_gap_points == pytest.approx(32.0)
    assert prediction.predicted_open == pytest.approx(24263.85)
    assert prediction.lower_gap_points == pytest.approx(20.0)
    assert prediction.upper_gap_points == pytest.approx(45.0)
    assert prediction.gap_class == GapClass.FLAT


def test_aug21_nifty_strict_score_preserves_interval_miss():
    prediction = build_gap_prediction(_snapshot())
    score = score_gap_prediction(prediction, actual_open=24284.05)

    assert score.actual_gap_points == pytest.approx(52.20)
    assert score.sign_correct is True
    # +32 is inside the +/-0.15% flat band; the actual +52.2 is outside it.
    assert score.class_correct is False
    assert score.central_abs_error_points == pytest.approx(20.20)
    assert score.interval_hit is False
    assert score.interval_miss_distance_points == pytest.approx(7.20)


def test_future_gift_data_fails_closed():
    cutoff = _snapshot().cutoff_ts
    prediction = build_gap_prediction(_snapshot(gift_ts=cutoff + timedelta(seconds=1)))

    assert prediction.status == "ABSTAIN"
    assert prediction.gap_class == GapClass.ABSTAIN
    assert "FUTURE_DATA_VIOLATION" in prediction.reasons


def test_stale_gift_data_fails_closed():
    cutoff = _snapshot().cutoff_ts
    prediction = build_gap_prediction(
        _snapshot(gift_ts=cutoff - timedelta(minutes=11), max_gift_age_seconds=600)
    )

    assert prediction.status == "ABSTAIN"
    assert "STALE_GIFT_DATA" in prediction.reasons


def test_unsafe_authority_fails_closed():
    prediction = build_gap_prediction(
        _snapshot(authority=EvidenceAuthority(allowed_for_live_execution=True))
    )

    assert prediction.status == "ABSTAIN"
    assert "LIVE_EXECUTION_AUTHORITY_FORBIDDEN" in prediction.reasons


def test_nifty_gap_rejection_is_measured_separately_from_prediction():
    response = measure_gap_response(
        index="NIFTY",
        previous_close=24231.85,
        actual_open=24284.05,
        current_price=24233.20,
        predicted_gap_points=32.0,
    )

    assert response.actual_gap_points == pytest.approx(52.20)
    assert response.gap_surprise_points == pytest.approx(20.20)
    assert response.retention_ratio == pytest.approx(1.35 / 52.20)
    assert response.fill_ratio == pytest.approx(1 - (1.35 / 52.20))
    assert response.state == GapResponseState.REJECTING


def test_banknifty_gap_retention_is_not_confused_with_nifty_gap_rejection():
    response = measure_gap_response(
        index="BANKNIFTY",
        previous_close=57495.90,
        actual_open=57613.20,
        current_price=57592.25,
    )

    assert response.actual_gap_points == pytest.approx(117.30)
    assert response.retention_ratio == pytest.approx(96.35 / 117.30)
    assert response.state == GapResponseState.RETAINING


def test_sensex_cross_below_previous_close_is_overfilled():
    response = measure_gap_response(
        index="SENSEX",
        previous_close=77537.72,
        actual_open=77701.07,
        current_price=77508.95,
    )

    assert response.actual_gap_points == pytest.approx(163.35)
    assert response.retention_ratio < 0
    assert response.fill_ratio > 1
    assert response.state == GapResponseState.OVERFILLED
