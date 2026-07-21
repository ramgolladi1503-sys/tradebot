from __future__ import annotations

import json
from pathlib import Path


BASE = Path("research/prospective_structural_edge_v2")


def test_cycle6_no_rejected_descendant_was_evaluated():
    quality = json.loads((BASE / "cycle6_hypothesis_quality_audit.json").read_text())
    rejection = json.loads((BASE / "cycle_6_rejection_analysis.json").read_text())

    assert quality["AC25"] == "REJECTED_OUTCOME_DEPENDENT_DESCENDANT"
    assert quality["AC26"] == "REJECTED_OUTCOME_DEPENDENT_DESCENDANT"
    assert quality["AC27"] == "REJECTED_EXHAUSTED_MECHANISM_FAMILY"
    assert quality["evaluated_hypotheses"] == []
    assert rejection["evaluated_hypotheses"] == []


def test_cycle6_replacement_inventory_has_no_same_corpus_open_family():
    inventory = json.loads((BASE / "cycle6_open_observable_state_inventory.json").read_text())
    replacements = json.loads((BASE / "cycle6_replacement_candidate_audit.json").read_text())

    assert inventory["scientifically_remaining_same_corpus_families"] == []
    assert replacements["replacement_hypotheses"] == []
    assert replacements["replacement_generation_verdict"] == "NO_SCIENTIFICALLY_OPEN_SAME_CORPUS_FAMILY"


def test_cycle6_quality_audit_is_pre_outcome():
    quality = json.loads((BASE / "cycle6_hypothesis_quality_audit.json").read_text())

    assert quality["outcomes_read_before_contract_freeze"] is False
    assert quality["parameters_optimized"] is False
