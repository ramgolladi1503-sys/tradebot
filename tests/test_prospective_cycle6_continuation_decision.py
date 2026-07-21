from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")


def test_cycle6_search_exhaustion_decision():
    decision = json.loads((BASE / "cycle_7_continuation_decision.json").read_text())
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert decision["result"] == "SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE"
    assert decision["cycle7_started"] is False
    assert final["FINAL_VERDICT"] == "SEARCH_UNIVERSE_EXHAUSTED_WITH_EVIDENCE"
    assert final["cycle7_started"] is False
    assert final["mechanism_families_still_scientifically_open"] == []


def test_cycle6_lockbox_and_option_boundaries():
    final = json.loads((BASE / "final_verdict.json").read_text())

    assert final["prospective_lockbox_opened"] is False
    assert final["old_lockbox_reused"] is False
    assert final["bid_ask_required"] is False
    assert final["option_data_used"] is False
    assert final["option_economic_certification"] == "OUT_OF_SCOPE"


def test_cycle6_independent_audit_passes():
    audit = json.loads((BASE / "determinism_report.json").read_text())

    assert audit["determinism"] == "PASS"
    assert audit["independent_outcome_dependency_audit"] == "PASS"
    assert audit["no_post_outcome_descendant_evaluated"] is True
