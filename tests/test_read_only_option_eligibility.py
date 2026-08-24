from core.read_only_option_eligibility import build_option_surface, evaluate_candidate_eligibility


def test_option_and_eligibility_boundaries_fail_closed():
    candidate = {"candidate_id": "c1", "underlying": "NIFTY"}
    surface = build_option_surface(candidate=candidate, option_evidence=None)
    assert surface["verdict"] == "PENDING"
    eligibility = evaluate_candidate_eligibility(candidate=candidate, option_surface=surface, regime={})
    assert eligibility["status"] == "advisory_only"
    assert "option_surface_not_ready" in eligibility["blockers"]

