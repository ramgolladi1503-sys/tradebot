from datetime import datetime, timezone

import pytest

from core.cas_v2_consumer_contract import freeze_cas_decision


FREEZE = datetime(2026, 8, 24, 9, 44, tzinfo=timezone.utc)  # 15:14 IST


def test_cas_freeze_uses_only_prior_completed_inputs_and_maps_ce():
    decision = freeze_cas_decision(
        completed_inputs={
            "15:10": datetime(2026, 8, 24, 9, 40, tzinfo=timezone.utc),
            "15:13": datetime(2026, 8, 24, 9, 43, tzinfo=timezone.utc),
        }, freeze_timestamp=FREEZE, direction="UP", source_sha="a" * 40, spec_sha="b" * 40,
    )
    assert decision.option_side == "CE"
    assert decision.execution_status == "advisory_only"


def test_cas_freeze_rejects_input_at_or_after_boundary():
    with pytest.raises(ValueError, match="after_freeze"):
        freeze_cas_decision(
            completed_inputs={"15:14": FREEZE}, freeze_timestamp=FREEZE,
            direction="DOWN", source_sha="a" * 40, spec_sha="b" * 40,
        )


def test_flat_and_abstain_have_no_option_side():
    for direction in ("FLAT", "ABSTAIN"):
        decision = freeze_cas_decision(
            completed_inputs={"15:13": FREEZE.replace(minute=43)}, freeze_timestamp=FREEZE,
            direction=direction, source_sha="a" * 40, spec_sha="b" * 40,
        )
        assert decision.option_side is None
