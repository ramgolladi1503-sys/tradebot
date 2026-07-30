import pytest

from core.runtime_hardening_campaign import build_hardening_campaign_report


def test_complete_shadow_campaign_passes_without_feed_changes():
    report = build_hardening_campaign_report(
        changed_paths=[
            "core/canonical_execution_decision.py",
            "tests/test_canonical_execution_decision.py",
        ],
        characterization_repeatable=True,
        canonical_decision_tests_passed=True,
        stage_pipeline_tests_passed=True,
        fault_tests_passed=True,
    )
    assert report["verdict"] == "PASS_SHADOW_HARDENING"
    assert report["feed_boundary_frozen"] is True
    assert report["allowed_for_live_execution"] is False
    assert report["broker_api_called"] is False
    assert all(stage["status"] != "FAIL" for stage in report["stages"])


def test_campaign_rejects_feed_modification():
    with pytest.raises(AssertionError, match="feed_boundary_modified"):
        build_hardening_campaign_report(
            changed_paths=["core/kite_depth_ws.py"],
            characterization_repeatable=True,
            canonical_decision_tests_passed=True,
            stage_pipeline_tests_passed=True,
            fault_tests_passed=True,
        )


def test_campaign_fails_when_characterization_is_not_repeatable():
    report = build_hardening_campaign_report(
        changed_paths=[],
        characterization_repeatable=False,
        canonical_decision_tests_passed=True,
        stage_pipeline_tests_passed=True,
        fault_tests_passed=True,
    )
    assert report["verdict"] == "FAIL_SHADOW_HARDENING"
    assert "C_CHARACTERIZATION" in report["hard_failures"]
