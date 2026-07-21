from __future__ import annotations

from research.independent_underlying_evaluation_v3.statistics import concentration, seed_for, sign_flip_p_value, summarize


def test_seed_derivation_is_deterministic_and_candidate_specific():
    a = seed_for("manifest", "AC24", "bootstrap")
    assert a == seed_for("manifest", "AC24", "bootstrap")
    assert a != seed_for("manifest", "AC16", "bootstrap")


def test_sign_flip_is_deterministic():
    rows = [{"session_date": f"2024-01-{i:02d}", "outcome_bps": float(i)} for i in range(1, 8)]
    first = sign_flip_p_value(rows, "manifest", "AC24", assignments_limit=1000)
    second = sign_flip_p_value(rows, "manifest", "AC24", assignments_limit=1000)
    assert first == second


def test_concentration_fails_single_index_dominance():
    rows = [{"session_date": f"2024-01-{i:02d}", "outcome_bps": 1.0, "target_symbol": "NIFTY", "direction": 1} for i in range(1, 11)]
    assert concentration(rows)["verdict"] == "FAIL"


def test_strict_pass_boundaries_reject_nonpositive_mean():
    rows = [{"session_date": f"2024-01-{i:02d}", "outcome_bps": -1.0, "mfe_bps": 0.0, "mae_bps": -2.0, "target_symbol": "NIFTY", "direction": 1} for i in range(1, 42)]
    result = summarize(rows, 0.006, "manifest", "AC24")
    assert result["verdict"] == "REJECTED_INDEPENDENT_SAMPLE_FAILURE"

