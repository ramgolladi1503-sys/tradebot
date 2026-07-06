from __future__ import annotations

from pathlib import Path

from scripts.run_option_data_quality_proof_pack import build_proof_pack


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "option_data_quality_candidate_proof_pack"


def test_option_data_quality_proof_pack_preserves_and_blocks_unsafe_quote_states():
    proof = build_proof_pack(FIXTURE_DIR)
    scenarios = {scenario["scenario"]: scenario for scenario in proof["scenarios"]}

    assert set(scenarios) == {
        "no_quote_preserved",
        "spread_wide_preserved",
        "iv_surface_slope_preserved",
        "iv_term_missing_preserved",
        "clean_live_quote",
    }

    assert scenarios["clean_live_quote"]["counts"]["raw_candidate_count"] == 1
    assert scenarios["clean_live_quote"]["counts"]["executable_rank_count"] == 1
    assert scenarios["clean_live_quote"]["execution_grade"]["state"] == "EXECUTION_GRADE"

    for name in ("no_quote_preserved", "spread_wide_preserved", "iv_surface_slope_preserved", "iv_term_missing_preserved"):
        scenario = scenarios[name]
        assert scenario["counts"]["raw_candidate_count"] >= 1
        assert scenario["counts"]["ranked_candidate_count"] >= 1
        assert scenario["execution_grade"]["execution_grade"] is False
        assert scenario["execution_grade"]["state"] in {"BLOCKED", "ADVISORY_ONLY"}
        assert scenario["report"]["ranking"]["ranks"][0]["executable_candidate"] is False

    assert scenarios["clean_live_quote"]["report"]["ranking"]["ranks"][0]["executable_candidate"] is True


def test_option_data_quality_proof_pack_keeps_blockers_visible_in_ranking():
    proof = build_proof_pack(FIXTURE_DIR)
    scenarios = {scenario["scenario"]: scenario for scenario in proof["scenarios"]}

    assert "QUOTE_SOURCE_UNTRUSTED" in scenarios["no_quote_preserved"]["execution_grade"]["blockers"]
    assert "WIDE_SPREAD" in scenarios["spread_wide_preserved"]["execution_grade"]["blockers"]
    assert "IV_SURFACE_SLOPE" in scenarios["iv_surface_slope_preserved"]["execution_grade"]["blockers"] or scenarios["iv_surface_slope_preserved"]["execution_grade"]["state"] == "BLOCKED"
    assert "UNRESOLVED_CONTRACT" in scenarios["iv_term_missing_preserved"]["execution_grade"]["blockers"]
