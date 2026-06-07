from __future__ import annotations

import math

from core.candidate_outcome_truth import (
    INVALID_INPUT,
    NOT_EXECUTABLE,
    STOP_HIT,
    TARGET_HIT,
    TIMEOUT,
    CandidateOutcomeInput,
    PriceObservation,
    build_candidate_outcome_truth,
    normalize_outcome_direction,
)


def _candidate(**overrides: object) -> CandidateOutcomeInput:
    payload = {
        "candidate_id": "cand-1",
        "trade_id": "trade-1",
        "strategy_family": "breakout",
        "symbol": "NIFTY",
        "index": "NIFTY",
        "regime": "BULLISH",
        "expiry_type": "WEEKLY",
        "signal_epoch": 100.0,
        "entry_price": 100.0,
        "stop_loss_price": 95.0,
        "target_price": 110.0,
        "timeout_epoch": 200.0,
        "feed_truth_state": "LIVE",
        "reportable_executable": True,
        "execution_allowed": True,
    }
    payload.update(overrides)
    return CandidateOutcomeInput(**payload)


def _safe_flags(payload: dict[str, object]) -> None:
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_long_target_above_entry_hits_target() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(direction="BUY"),
        [PriceObservation(observed_epoch=101.0, ltp=111.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TARGET_HIT
    assert truth.target_hit is True
    assert truth.stop_hit is False
    assert math.isclose(truth.gross_r, 2.0)


def test_long_stop_below_entry_hits_stop() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(direction="LONG"),
        [PriceObservation(observed_epoch=101.0, ltp=94.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == STOP_HIT
    assert truth.stop_hit is True
    assert truth.target_hit is False
    assert math.isclose(truth.gross_r, -1.0)


def test_short_target_below_entry_hits_target() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(
            direction="SELL",
            entry_price=100.0,
            stop_loss_price=105.0,
            target_price=90.0,
        ),
        [PriceObservation(observed_epoch=101.0, ltp=89.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TARGET_HIT
    assert truth.target_hit is True
    assert truth.stop_hit is False
    assert math.isclose(truth.gross_r, 2.0)


def test_short_stop_above_entry_hits_stop() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(
            direction="SHORT",
            entry_price=100.0,
            stop_loss_price=106.0,
            target_price=92.0,
        ),
        [PriceObservation(observed_epoch=101.0, ltp=107.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == STOP_HIT
    assert truth.stop_hit is True
    assert truth.target_hit is False
    assert truth.gross_r == -1.0


def test_short_timeout_gross_r_computed_correctly() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(
            direction="SELL_CALL",
            entry_price=100.0,
            stop_loss_price=106.0,
            target_price=92.0,
        ),
        [
            PriceObservation(observed_epoch=101.0, ltp=97.0),
            PriceObservation(observed_epoch=199.0, ltp=94.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TIMEOUT
    assert math.isclose(truth.gross_r, 1.0)
    assert math.isclose(truth.cost_adjusted_r, truth.gross_r)
    assert truth.max_favorable_price == 94.0
    assert truth.max_adverse_price == 97.0


def test_invalid_short_risk_model_fails_closed() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(
            direction="SELL_PUT",
            entry_price=100.0,
            stop_loss_price=95.0,
            target_price=110.0,
        ),
        [PriceObservation(observed_epoch=101.0, ltp=99.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == INVALID_INPUT
    assert "INVALID_RISK_MODEL" in truth.blockers
    assert truth.outcome_reason == "invalid_short_risk_model"


def test_unsupported_direction_fails_closed() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(direction="NEUTRAL"),
        [PriceObservation(observed_epoch=101.0, ltp=99.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == INVALID_INPUT
    assert "UNSUPPORTED_DIRECTION" in truth.blockers
    assert truth.outcome_reason == "unsupported_direction"


def test_buy_put_defaults_to_long_option_math_unless_underlying_direction_overrides() -> None:
    long_like = build_candidate_outcome_truth(
        _candidate(direction="BUY_PUT", entry_price=10.0, stop_loss_price=8.0, target_price=13.0),
        [PriceObservation(observed_epoch=101.0, ltp=13.0)],
    )
    short_like = build_candidate_outcome_truth(
        _candidate(
            direction="BUY_PUT",
            underlying_direction="SELL",
            entry_price=10.0,
            stop_loss_price=12.0,
            target_price=8.0,
        ),
        [PriceObservation(observed_epoch=101.0, ltp=8.0)],
    )

    _safe_flags(long_like.to_payload())
    _safe_flags(short_like.to_payload())
    assert normalize_outcome_direction(_candidate(direction="BUY_PUT")) == "BUY"
    assert normalize_outcome_direction(_candidate(direction="BUY_PUT", underlying_direction="SELL")) == "SELL"
    assert long_like.outcome_status == TARGET_HIT
    assert short_like.outcome_status == TARGET_HIT
