import pytest

from research.mros_certification.prospective import ProspectiveLedger


def test_prospective_ledger_is_immutable_and_binds_frozen_spec():
    ledger = ProspectiveLedger(frozen_spec_sha="s" * 64)
    next_ledger = ledger.append({"session": "2026-08-12", "spec_sha": "s" * 64})
    assert ledger.entries == ()
    assert next_ledger.entries[0]["immutable"] is True
    assert next_ledger.attach_outcome(next_ledger.entries[0]["prediction_sha"], {"value": 1}).entries[0]["outcome"]["value"] == 1


@pytest.mark.parametrize("prediction,error", [
    ({"spec_sha": "x" * 64}, "PROSPECTIVE_SPEC_MISMATCH"),
    ({"spec_sha": "s" * 64, "outcome": {"value": 1}}, "OUTCOME_CONDITIONED_PREDICTION_FORBIDDEN"),
])
def test_prospective_ledger_rejects_unsafe_inputs(prediction, error):
    with pytest.raises(ValueError, match=error):
        ProspectiveLedger(frozen_spec_sha="s" * 64).append(prediction)
