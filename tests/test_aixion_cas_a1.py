from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import json

import pytest

from aixion_trade_intelligence.cas_a1 import (
    EXPECTATION_INTERCEPT,
    EXPECTATION_SLOPE,
    FROZEN_SPEC_PAYLOAD,
    FROZEN_SPEC_SHA256,
    SPEC_VERSION,
    CasA1ContractError,
    CasA1EvidenceError,
    CasA1Observation,
    ConstituentMark,
    build_cas_a1_events,
    cumulative_summary,
    evaluate_cas_a1,
    write_prospective_result,
)


def _constituents():
    return [f"NSE_EQ|C{i:02d}" for i in range(49)]


def _contract():
    return {
        "cas_a1": {
            "enabled": True,
            **FROZEN_SPEC_PAYLOAD,
            "spec_sha256": FROZEN_SPEC_SHA256,
            "frozen_constituents": _constituents(),
        }
    }


def _dt(hour: int, minute: int, second: int = 0):
    local = datetime(2026, 8, 18, hour, minute, second, tzinfo=ZoneInfo("Asia/Kolkata"))
    return local.astimezone(timezone.utc)


def _observation(*, end_price: float = 100.01):
    marks = tuple(
        ConstituentMark(
            instrument_key=key,
            price_1510=100.0,
            price_1514=end_price,
            source_event_ids=(),
        )
        for key in _constituents()
    )
    return CasA1Observation(
        session_id="2026-08-18",
        session_date="2026-08-18",
        index_instrument="NSE_INDEX|Nifty 50",
        futures_instrument="NSE_FO|NIFTY_AUG_FUT",
        constituent_marks=marks,
        nifty_1514=25000.0,
        nifty_1514_available_time=_dt(15, 15, 0),
        final_cas_index=25075.0,
        final_cas_available_time=_dt(15, 29, 2),
        future_1529=25040.0,
        future_1529_available_time=_dt(15, 29, 3),
        future_1539=25050.0,
        future_1539_available_time=_dt(15, 39, 2),
        source_provider="KITE_READ_ONLY",
    )


def test_frozen_formula_is_exact_and_no_authority_is_created():
    observation = _observation()
    result = evaluate_cas_a1(observation, _contract())
    ew = (100.01 / 100.0 - 1.0) * 10000.0
    expected = EXPECTATION_INTERCEPT + EXPECTATION_SLOPE * ew
    assert result.equal_weight_return_1510_1514_bps == pytest.approx(ew)
    assert result.expected_cas_adjustment_bps == pytest.approx(expected)
    assert result.spec_version == SPEC_VERSION
    assert result.spec_sha256 == FROZEN_SPEC_SHA256
    assert result.broker_write_authority is False
    assert result.order_authority is False
    assert result.paper_authorized is False
    assert result.live_authorized is False
    assert result.prospective_supported is False
    assert result.structural_edge_certified is False


def test_formula_coefficient_drift_is_rejected():
    contract = _contract()
    contract["cas_a1"]["expectation_slope"] = EXPECTATION_SLOPE + 0.0001
    with pytest.raises(CasA1ContractError, match="frozen contract drift"):
        evaluate_cas_a1(_observation(), contract)


def test_threshold_or_prediction_rule_drift_is_rejected():
    contract = _contract()
    contract["cas_a1"]["prediction_rule"] = "SURPRISE_GT_5_BPS"
    with pytest.raises(CasA1ContractError, match="frozen contract drift"):
        evaluate_cas_a1(_observation(), contract)


def test_missing_one_constituent_fails_closed_not_zero():
    observation = _observation()
    observation = replace(observation, constituent_marks=observation.constituent_marks[:-1])
    with pytest.raises(CasA1EvidenceError, match="FROZEN_CONSTITUENT"):
        evaluate_cas_a1(observation, _contract())


def test_nonpositive_or_nonfinite_marks_are_rejected_not_coerced():
    observation = _observation()
    marks = list(observation.constituent_marks)
    marks[0] = replace(marks[0], price_1514=0.0)
    with pytest.raises(CasA1EvidenceError, match="finite and positive"):
        evaluate_cas_a1(replace(observation, constituent_marks=tuple(marks)), _contract())


def test_final_cas_cannot_be_available_before_1528_ist():
    observation = replace(_observation(), final_cas_available_time=_dt(15, 27, 59))
    with pytest.raises(CasA1EvidenceError, match="FINAL_CAS_AVAILABLE_BEFORE"):
        evaluate_cas_a1(observation, _contract())


def test_target_1529_cannot_precede_final_cas_prediction_availability():
    observation = replace(
        _observation(),
        final_cas_available_time=_dt(15, 29, 10),
        future_1529_available_time=_dt(15, 29, 5),
    )
    with pytest.raises(CasA1EvidenceError, match="TARGET_START_PRECEDES_PREDICTION"):
        evaluate_cas_a1(observation, _contract())


def test_target_1539_must_be_causally_available_at_or_after_1539():
    observation = replace(_observation(), future_1539_available_time=_dt(15, 38, 59))
    with pytest.raises(CasA1EvidenceError, match="FUTURE_1539_AVAILABLE_TOO_EARLY"):
        evaluate_cas_a1(observation, _contract())


def test_cross_session_evidence_is_rejected():
    bad_time = datetime(2026, 8, 19, 10, 9, 2, tzinfo=timezone.utc)
    observation = replace(_observation(), future_1539_available_time=bad_time)
    with pytest.raises(CasA1EvidenceError, match="CROSS_SESSION_TIMESTAMP"):
        evaluate_cas_a1(observation, _contract())


def test_prediction_does_not_change_when_only_future_outcome_changes():
    base = evaluate_cas_a1(_observation(), _contract())
    losing = evaluate_cas_a1(replace(_observation(), future_1539=24900.0), _contract())
    assert base.auction_surprise_bps == pytest.approx(losing.auction_surprise_bps)
    assert base.prediction == losing.prediction
    assert base.actual_sign != losing.actual_sign
    assert base.correct != losing.correct


def test_canonical_event_chain_prediction_precedes_outcome_and_is_research_only():
    events = build_cas_a1_events(_observation(), _contract())
    assert [event.event_type for event in events] == [
        "CAS_A1_EXPECTATION_FROZEN",
        "CAS_FINAL_PRICE_OBSERVED",
        "CAS_A1_SURPRISE_OBSERVED",
        "CAS_A1_PREDICTION_FROZEN",
        "CAS_A1_OUTCOME_OBSERVED",
    ]
    prediction = events[-2]
    outcome = events[-1]
    assert prediction.event_id in outcome.parent_event_ids
    assert prediction.available_time < outcome.available_time
    assert prediction.payload["broker_write_authority"] is False
    assert prediction.payload["order_authority"] is False
    assert prediction.payload["live_authorized"] is False
    assert "actual_sign" not in prediction.payload
    assert outcome.payload["prospective_supported"] is False


def test_prospective_result_is_idempotent_and_conflict_rejected(tmp_path: Path):
    result = evaluate_cas_a1(_observation(), _contract())
    path1 = write_prospective_result(result=result, output_dir=tmp_path)
    path2 = write_prospective_result(result=result, output_dir=tmp_path)
    assert path1 == path2

    raw = json.loads(path1.read_text())
    raw["prediction"] = "DOWN" if raw["prediction"] == "UP" else "UP"
    path1.write_text(json.dumps(raw))
    with pytest.raises(CasA1EvidenceError, match="immutable prospective result conflict"):
        write_prospective_result(result=result, output_dir=tmp_path)


def test_cumulative_summary_keeps_development_and_prospective_separate(tmp_path: Path):
    result = evaluate_cas_a1(_observation(), _contract())
    write_prospective_result(result=result, output_dir=tmp_path)
    summary = cumulative_summary(tmp_path)
    assert summary["prospective_sessions"] == 1
    assert summary["development_sessions"] == 10
    assert summary["development_alignment"] == "9/10"
    assert summary["development_and_prospective_pooled"] is False
    assert summary["prospective_supported"] is False
    assert summary["structural_edge_certified"] is False
