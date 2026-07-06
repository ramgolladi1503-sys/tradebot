from __future__ import annotations

from pathlib import Path

from scripts.run_candidate_ranking_proof_pack import build_proof_pack


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ranked_pipeline_contract_proof_pack"


def test_candidate_to_ranking_proof_pack_is_deterministic_and_non_empty():
    proof = build_proof_pack(FIXTURE_DIR)
    scenarios = {scenario["scenario"]: scenario for scenario in proof["scenarios"]}

    assert set(scenarios) == {"clean_ranking", "fallback_blocked", "unresolved_blocked"}
    assert scenarios["clean_ranking"]["read_only"] is True
    assert scenarios["clean_ranking"]["is_order_action"] is False
    assert scenarios["clean_ranking"]["append"] is False
    assert scenarios["clean_ranking"]["counts"]["raw_candidate_count"] == 1
    assert scenarios["clean_ranking"]["counts"]["ranked_candidate_count"] == 1
    assert scenarios["clean_ranking"]["counts"]["executable_rank_count"] == 1
    assert scenarios["clean_ranking"]["ranking"]["top_rank_strategy_id"] == "clean_exec"
    assert [row["strategy_id"] for row in scenarios["clean_ranking"]["ranking"]["ranks"]] == ["clean_exec"]
    assert scenarios["fallback_blocked"]["counts"]["raw_candidate_count"] == 2
    assert scenarios["fallback_blocked"]["counts"]["executable_rank_count"] == 0
    assert scenarios["unresolved_blocked"]["counts"]["raw_candidate_count"] == 1
    assert scenarios["unresolved_blocked"]["counts"]["executable_rank_count"] == 0


def test_candidate_to_ranking_proof_pack_preserves_blocked_candidates_but_never_upgrades_them():
    proof = build_proof_pack(FIXTURE_DIR)
    scenarios = {scenario["scenario"]: scenario for scenario in proof["scenarios"]}
    fallback = scenarios["fallback_blocked"]
    unresolved = scenarios["unresolved_blocked"]

    assert fallback["ranking"]["ranks"][0]["bucket"] == "SUPPRESSED_CANDIDATE"
    assert fallback["ranking"]["ranks"][0]["executable_candidate"] is False
    assert fallback["ranking"]["ranks"][-1]["bucket"] == "NO_TRADE_CANDIDATE"
    assert unresolved["ranking"]["ranks"][0]["bucket"] == "SUPPRESSED_CANDIDATE"
    assert unresolved["ranking"]["ranks"][0]["executable_candidate"] is False
    assert "FALLBACK_QUOTE_ONLY" in fallback["blockers"]
    assert "UNRESOLVED_CONTRACT" in unresolved["blockers"]
