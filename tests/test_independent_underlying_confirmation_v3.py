from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/independent_underlying_confirmation_v3")


def test_exhausted_epoch_is_closed_and_no_cycle7():
    handoff = json.loads((BASE / "exhausted_epoch_handoff.json").read_text())
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert handoff["same_corpus_search_status"] == "CLOSED"
    assert handoff["new_same_corpus_hypotheses_allowed"] is False
    assert handoff["same_corpus_parameter_variants_allowed"] is False
    assert final["cycle7_generated"] is False


def test_confirmation_candidates_and_alpha_are_frozen():
    registry = json.loads((BASE / "confirmation_candidate_registry.json").read_text())

    ids = [row["hypothesis_id"] for row in registry["confirmation_candidates"]]
    assert ids == [
        "AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION",
        "AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION",
    ]
    assert registry["alpha_allocation"]["AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION"] == 0.006
    assert registry["alpha_allocation"]["AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION"] == 0.004
    assert registry["unused_alpha_reassignment_allowed"] is False


def test_old_corpus_generator_equivalence_passes():
    equivalence = json.loads((BASE / "frozen_generator_equivalence.json").read_text())

    assert equivalence["verdict"] == "PASS"
    assert equivalence["checks"]["AC24_PRIOR_SESSION_BODY_MIDPOINT_REJECTION"]["candidate_count_exact_match"] is True
    assert equivalence["checks"]["AC16_PRIOR_EXTREME_ACCEPTANCE_VWAP_MIGRATION"]["candidate_count_exact_match"] is True


def test_epoch_waits_for_unseen_data_and_is_not_opened():
    readiness = json.loads((BASE / "confirmation_readiness.json").read_text())
    contract = json.loads((BASE / "independent_epoch_contract.json").read_text())

    assert readiness["verdict"] == "WAITING_FOR_INDEPENDENT_UNSEEN_DATA"
    assert readiness["session_gate_pass"] is False
    assert readiness["calendar_gate_pass"] is False
    assert contract["sealed"] is False
    assert contract["opened"] is False
