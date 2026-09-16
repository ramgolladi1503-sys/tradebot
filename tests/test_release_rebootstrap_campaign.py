from scripts.release_rebootstrap_mutation_campaign import ATTACKS


def test_rebootstrap_attack_registry_is_complete_and_unique():
    assert len(ATTACKS) == 22
    assert len(set(ATTACKS)) == 22


def test_required_attack_classes_present():
    required={"healthy_head","head_not_quarantined","candidate_sha_mismatch","dependency_graph_incomplete","primitive_missing","caller_authored_pass","arbitrary_gate_runner","generic_evidence_reuse","primitive_hash_changed","evaluator_identity_changed","gate_result_changed","attestation_changed","predecessor_event_changed","predecessor_sha_changed","history_event_removed","history_event_reordered","recovery_event_replayed","second_rebootstrap","quarantined_fallback","nonzero_safety_counter","unattested_current_pointer"}
    assert required.issubset(set(ATTACKS))
