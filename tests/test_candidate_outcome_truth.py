from __future__ import annotations

import math

from core.candidate_outcome_truth import (
    AMBIGUOUS_SAME_BAR,
    CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION,
    INVALID_INPUT,
    NO_OBSERVATIONS,
    NOT_EXECUTABLE,
    STOP_HIT,
    TARGET_HIT,
    TIMEOUT,
    CandidateOutcomeInput,
    PriceObservation,
    build_candidate_outcome_truth,
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
        "side": "BUY",
        "feed_truth_state": "LIVE",
        "reportable_executable": True,
        "execution_allowed": True,
        "estimated_cost_r": 0.25,
    }
    payload.update(overrides)
    return CandidateOutcomeInput(**payload)


def _safe_flags(payload: dict[str, object]) -> None:
    assert payload["schema_version"] == CANDIDATE_OUTCOME_TRUTH_SCHEMA_VERSION
    assert payload["read_only"] is True
    assert payload["append"] is False
    assert payload["is_order_action"] is False
    assert payload["broker_api_called"] is False
    assert payload["live_order_allowed"] is False
    assert payload["live_order_action"] is False
    assert payload["broker_order_action"] is False


def test_target_hit_before_stop() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(),
        [
            PriceObservation(observed_epoch=101.0, ltp=104.0),
            PriceObservation(observed_epoch=102.0, ltp=110.0),
            PriceObservation(observed_epoch=103.0, ltp=96.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TARGET_HIT
    assert truth.target_hit is True
    assert truth.stop_hit is False
    assert truth.gross_r > 0
    assert math.isclose(truth.gross_r, 2.0)
    assert math.isclose(truth.cost_adjusted_r, truth.gross_r - 0.25)


def test_stop_hit_before_target() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(),
        [
            PriceObservation(observed_epoch=101.0, ltp=98.0),
            PriceObservation(observed_epoch=102.0, ltp=94.0),
            PriceObservation(observed_epoch=103.0, ltp=112.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == STOP_HIT
    assert truth.stop_hit is True
    assert truth.target_hit is False
    assert truth.gross_r == -1.0


def test_timeout_with_mfe_and_mae_calculated() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(estimated_cost_r=None),
        [
            PriceObservation(observed_epoch=101.0, ltp=103.0),
            PriceObservation(observed_epoch=102.0, ltp=97.0),
            PriceObservation(observed_epoch=199.0, ltp=104.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TIMEOUT
    assert truth.timeout_hit is True
    assert truth.target_hit is False
    assert truth.stop_hit is False
    assert math.isclose(truth.mfe_abs, 4.0)
    assert math.isclose(truth.mae_abs, 3.0)
    assert math.isclose(truth.gross_r, 0.8)
    assert math.isclose(truth.cost_adjusted_r, truth.gross_r)


def test_no_observations() -> None:
    truth = build_candidate_outcome_truth(_candidate(), [])

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == NO_OBSERVATIONS
    assert truth.observation_count == 0
    assert "NO_OBSERVATIONS" in truth.blockers


def test_not_executable_candidate_returns_not_executable() -> None:
    truth = build_candidate_outcome_truth(_candidate(reportable_executable=False), [PriceObservation(observed_epoch=101.0, ltp=120.0)])

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == NOT_EXECUTABLE
    assert truth.target_hit is False
    assert truth.stop_hit is False
    assert "NOT_EXECUTABLE" in truth.blockers


def test_invalid_missing_price_fields() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(entry_price=None, stop_loss_price=95.0, target_price=110.0),
        [PriceObservation(observed_epoch=101.0, ltp=120.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == INVALID_INPUT
    assert truth.blockers
    assert truth.outcome_reason == "missing_required_price_or_time_fields"


def test_ambiguous_same_bar_target_and_stop_hit() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(),
        [
            PriceObservation(observed_epoch=101.0, ltp=100.0, bid=94.0, ask=111.0, spread=17.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == AMBIGUOUS_SAME_BAR
    assert truth.target_hit is False
    assert truth.stop_hit is False
    assert truth.first_hit_epoch == 101.0
    assert truth.gross_r == 0.0


def test_cost_adjusted_r_lower_than_gross_r() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(estimated_cost_r=0.5),
        [
            PriceObservation(observed_epoch=101.0, ltp=110.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TARGET_HIT
    assert math.isclose(truth.cost_adjusted_r, truth.gross_r - 0.5)


def test_grouping_metadata_preserved() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(candidate_id="cand-9", trade_id="trade-9", strategy_family="mean_reversion", symbol="BANKNIFTY", index="BANKNIFTY", regime="BEARISH", expiry_type="MONTHLY"),
        [PriceObservation(observed_epoch=101.0, ltp=109.0)],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.candidate_id == "cand-9"
    assert truth.trade_id == "trade-9"
    assert truth.strategy_family == "mean_reversion"
    assert truth.symbol == "BANKNIFTY"
    assert truth.index == "BANKNIFTY"
    assert truth.regime == "BEARISH"
    assert truth.expiry_type == "MONTHLY"


def test_ignores_pre_signal_observations() -> None:
    truth = build_candidate_outcome_truth(
        _candidate(),
        [
            PriceObservation(observed_epoch=99.0, ltp=120.0),
            PriceObservation(observed_epoch=100.5, ltp=101.0),
            PriceObservation(observed_epoch=101.0, ltp=104.0),
            PriceObservation(observed_epoch=102.0, ltp=111.0),
        ],
    )

    payload = truth.to_payload()
    _safe_flags(payload)
    assert truth.outcome_status == TARGET_HIT
    assert truth.observation_count == 3
    assert truth.first_hit_epoch == 102.0

