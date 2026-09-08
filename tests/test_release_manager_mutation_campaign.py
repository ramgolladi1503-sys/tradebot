from scripts.release_manager_mutation_campaign import run_campaign


def test_release_manager_mutation_campaign_detects_all_cases():
    result = run_campaign()

    assert result["pass"] is True
    assert result["release_manager_mutations_detected"] == f"{result['total']}/{result['total']}"
    assert result["broker_api_called"] is False
    assert result["orders_placed"] == 0
    assert {case["name"] for case in result["cases"]} == {
        "candidate_certification_missing_required_gate",
        "promotion_attempted_before_complete_certification",
        "invalid_fallback_release",
        "manifest_points_to_uncertified_sha",
        "unknown_impact_requires_critical_gates",
        "invalid_changed_path_rejected",
        "history_tamper_detected",
    }
