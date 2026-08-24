import pytest

from core.live_candidate_contract import candidate_from_mapping


def _candidate(**overrides):
    row = {
        "candidate_id": "c1", "strategy_id": "CAS_SW_RUNTIME_V2_1514", "spec_sha": "b" * 40,
        "timestamp": "2026-08-24T15:14:00+05:30", "underlying": "NIFTY",
        "direction": "UP", "candidate_type": "directional_option", "confidence_raw": 0.7,
        "regime": "trend", "reason": "causal_inputs_complete", "data_cutoff": "2026-08-24T15:13:59+05:30",
    }
    row.update(overrides)
    return row


def test_common_candidate_preserves_strategy_provenance():
    candidate = candidate_from_mapping(_candidate())
    assert candidate.strategy_id == "CAS_SW_RUNTIME_V2_1514"
    assert candidate.execution_status == "advisory_only"


@pytest.mark.parametrize("field", ["strategy_id", "spec_sha", "data_cutoff"])
def test_candidate_requires_provenance(field):
    with pytest.raises(ValueError, match="provenance|identity"):
        candidate_from_mapping(_candidate(**{field: ""}))


def test_candidate_rejects_execution_status():
    with pytest.raises(ValueError, match="not_advisory"):
        candidate_from_mapping(_candidate(execution_status="live"))
