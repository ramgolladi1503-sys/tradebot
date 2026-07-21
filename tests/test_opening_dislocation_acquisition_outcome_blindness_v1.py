from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/opening_dislocation_reversal/data_acquisition")


def test_outcome_blindness_artifact_prohibits_strategy_calculation():
    audit = json.loads((BASE / "fresh_epoch_outcome_blindness_audit.json").read_text())
    assert audit["candidate_counts"] == "NOT_CALCULATED"
    assert audit["candidate_features"] == "NOT_CALCULATED"
    assert audit["strategy_outcomes"] == "NOT_CALCULATED"
    assert audit["strategy_imports"] == []
