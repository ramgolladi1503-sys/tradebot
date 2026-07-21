from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/opening_dislocation_reversal/data_acquisition")


def test_blocked_epoch_is_not_sealed_or_opened():
    final = json.loads((BASE / "final_verdict.json").read_text())
    assert final["FINAL_VERDICT"] in {
        "BLOCKED_HISTORICAL_CREDENTIAL_UNAVAILABLE",
        "PARTIAL_FRESH_DATA_ACQUIRED_NEED_EARLIER_HISTORY",
    }
    assert (final.get("data_epoch_sealed") or final.get("full_data_epoch_sealed")) is False
    assert final["holdout_opened"] is False
    assert (final.get("candidate_logic_run") or final.get("candidate_logic_implemented")) is False
    assert (final.get("outcomes_calculated") or final.get("strategy_outcomes_calculated")) is False


def test_no_parquet_committed_to_git():
    manifest = json.loads((BASE / "artifact_audit.json").read_text())
    assert manifest["raw_data_committed_to_git"] is False
