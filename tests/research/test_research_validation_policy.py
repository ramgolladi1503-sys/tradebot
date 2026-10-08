import math

import pytest

from core.research_validation.policy import (
    BLOCKED,
    FAIL,
    INCONCLUSIVE,
    CertificationInput,
    certify_research,
)


def _good(**overrides):
    base = dict(
        hypothesis_id="H-001",
        registered_experiments=12,
        declared_experiments=12,
        parameter_stability_pass=True,
        wfa_pass=True,
        pbo=0.10,
        psr=0.99,
        dsr=0.98,
        actual_track_record=500,
        minimum_track_record=200,
        power=0.90,
        cost_robust_pass=True,
        holdout_status="PASS",
        prospective_status="PASS",
        inference_model_valid=True,
        search_history_complete=True,
    )
    base.update(overrides)
    return CertificationInput(**base)


def test_complete_strong_evidence_can_only_certify_research_not_execution():
    verdict = certify_research(_good(), require_prospective=True)
    assert verdict.status == "CERTIFIED_RESEARCH"
    assert verdict.read_only is True
    assert verdict.is_order_action is False
    assert verdict.broker_api_called is False
    assert verdict.allowed_for_live_execution is False
    assert verdict.append is False


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"hypothesis_id": ""}, "MISSING_HYPOTHESIS_ID"),
        ({"registered_experiments": 0}, "MISSING_EXPERIMENT_HISTORY"),
        ({"declared_experiments": 13}, "SEARCH_HISTORY_INCOMPLETE"),
        ({"search_history_complete": False}, "SEARCH_HISTORY_INCOMPLETE"),
        ({"inference_model_valid": False}, "INFERENCE_MODEL_INVALID"),
    ],
)
def test_preflight_fails_closed(overrides, reason):
    verdict = certify_research(_good(**overrides))
    assert verdict.status == BLOCKED
    assert reason in verdict.reasons
    assert verdict.allowed_for_live_execution is False


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"parameter_stability_pass": False}, "PARAMETER_FRAGILE"),
        ({"wfa_pass": False}, "WFA_FAIL"),
        ({"pbo": 0.21}, "PBO_HIGH"),
        ({"psr": 0.949}, "PSR_FAIL"),
        ({"dsr": 0.949}, "DSR_FAIL"),
        ({"cost_robust_pass": False}, "COST_ROBUSTNESS_FAIL"),
        ({"holdout_status": "FAIL"}, "HOLDOUT_NOT_PASS"),
    ],
)
def test_any_hard_gate_failure_prevents_certification(overrides, reason):
    verdict = certify_research(_good(**overrides))
    assert verdict.status == FAIL
    assert reason in verdict.reasons


@pytest.mark.parametrize("field", ["pbo", "psr", "dsr", "power"])
@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -0.01, 1.01])
def test_missing_or_invalid_probability_evidence_never_certifies(field, bad):
    verdict = certify_research(_good(**{field: bad}))
    assert verdict.status in {BLOCKED, INCONCLUSIVE}
    assert verdict.status != "CERTIFIED_RESEARCH"


def test_too_short_track_record_is_inconclusive_not_failed():
    verdict = certify_research(_good(actual_track_record=50, minimum_track_record=200))
    assert verdict.status == INCONCLUSIVE
    assert "UNDERPOWERED" in verdict.reasons


def test_infinite_minimum_track_record_is_inconclusive():
    verdict = certify_research(_good(minimum_track_record=math.inf))
    assert verdict.status == INCONCLUSIVE
    assert "UNDERPOWERED" in verdict.reasons


def test_low_power_is_inconclusive_not_failed():
    verdict = certify_research(_good(power=0.25))
    assert verdict.status == INCONCLUSIVE
    assert verdict.gates["power"] == INCONCLUSIVE


def test_optional_prospective_not_run_does_not_block_historical_research_certification():
    verdict = certify_research(_good(prospective_status="NOT_RUN"), require_prospective=False)
    assert verdict.status == "CERTIFIED_RESEARCH"
    assert verdict.gates["prospective"] == INCONCLUSIVE


def test_required_prospective_not_run_fails():
    verdict = certify_research(_good(prospective_status="NOT_RUN"), require_prospective=True)
    assert verdict.status == FAIL
    assert "PROSPECTIVE_NOT_CONFIRMED" in verdict.reasons


def test_inconclusive_track_record_cannot_be_hidden_by_optional_prospective_gate():
    verdict = certify_research(
        _good(actual_track_record=20, minimum_track_record=100, prospective_status="NOT_RUN"),
        require_prospective=False,
    )
    assert verdict.status == INCONCLUSIVE


def test_additional_gate_is_fail_closed():
    verdict = certify_research(_good(additional_gates={"placebo": False, "leakage": True}))
    assert verdict.status == FAIL
    assert "ADDITIONAL_GATE_FAIL:placebo" in verdict.reasons


def test_threshold_boundaries_are_inclusive():
    verdict = certify_research(_good(pbo=0.20, psr=0.95, dsr=0.95, power=0.80))
    assert verdict.status == "CERTIFIED_RESEARCH"
