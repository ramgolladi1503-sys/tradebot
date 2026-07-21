from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/independent_underlying_confirmation_v3")


def test_session_novelty_excludes_exhausted_and_old_lockbox_sessions():
    novelty = json.loads((BASE / "session_novelty_audit.json").read_text())

    assert novelty["exhausted_corpus_excluded"] is True
    assert novelty["old_lockbox_excluded"] is True
    assert novelty["prior_outcome_use_detected"] is False
    assert novelty["session_novelty_verdict"] == "INSUFFICIENT_TRUSTWORTHY_UNSEEN_DATA"


def test_inventory_is_strategy_outcome_blind():
    inventory = json.loads((BASE / "unseen_data_inventory.json").read_text())

    assert inventory["strategy_outcome_blind"] is True
    assert inventory["candidate_counts_calculated"] is False
    assert inventory["eligible_independent_sessions"] == 0


def test_independent_manifest_is_append_only_and_empty_before_seal():
    manifest = json.loads((BASE / "independent_session_manifest.json").read_text())

    assert manifest["append_only"] is True
    assert manifest["opened"] is False
    assert manifest["sessions"] == []
