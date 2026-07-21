import json

from research.rsi2_mean_reversion.independent_publication_oracle_v2 import IMMUTABLE, V2, sha256_file


def test_immutable_baseline_hashes_remain_unchanged():
    manifest = next(IMMUTABLE.glob("*/immutable_baseline_manifest.json"))
    data = json.loads(manifest.read_text())

    for path, expected in data["immutable_files"].items():
        assert sha256_file(manifest.parent / path.split("/")[-1]) == expected


def test_promotion_shadow_execution_are_false_and_closure_prevents_tuning():
    report = json.loads((V2 / "final_publication_report_v2.json").read_text())
    closure = json.loads((V2 / "permanent_research_closure.json").read_text())

    assert report["promotion_eligible"] is False
    assert report["shadow_eligible"] is False
    assert report["execution_eligibility"] is False
    assert closure["RSI2_MEAN_REVERSION_EXACT_HYPOTHESIS"] == "PERMANENTLY_CLOSED_FOR_CURRENT_OBSERVABLE_DATA_FAMILY"
    assert closure["CURRENT_DATA_MAY_NOT_BE_USED_TO_TUNE_INVERT_OR_SELECT_NEW_RSI2_VARIANT"] is True
    assert "choosing inverted RSI because it looked better" in closure["explicit_prohibitions"]


def test_worktree_retirement_distinctions_are_correct():
    archive = json.loads((V2 / "research_component_archive_manifest_v2.json").read_text())
    retirement = json.loads((V2 / "worktree_retirement_readiness_v2.json").read_text())

    assert archive["generic_publication_architecture_candidate"]["merge_recommendation"] == "DEFERRED_TO_MAIN_ARCHITECTURE_REVIEW"
    assert retirement["readiness_verdict"] == "SAFE_TO_REMOVE_LOCAL_WORKTREE_AFTER_ARCHITECTURE_REVIEW"
    assert retirement["worktree_removed"] is False
