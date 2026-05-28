from __future__ import annotations

from tools.code_excellence.vulcan import HardeningInput, score_hardening


def test_silent_fallback_reduces_score_and_flags_reason():
    result = score_hardening(
        HardeningInput(
            changed_files=("tools/code_excellence/vulcan/hardening_score.py",),
            patch_text="def load():\n    return None\n",
            tests_changed=("tests/test_vulcan_hardening_score.py",),
        )
    )

    assert result.score < 80
    assert result.verdict == "WARN"
    assert result.production_grade_claim_allowed is False
    assert "silent_fallback_detected" in result.reasons


def test_fail_closed_behavior_and_negative_tests_increase_score():
    result = score_hardening(
        HardeningInput(
            changed_files=("tools/code_excellence/vulcan/hardening_score.py",),
            patch_text=(
                "def guard(value, enabled=False):\n"
                "    if not value:\n"
                "        raise ValueError('blocked_reason: value required')\n"
                "    return {'evidence': 'proof', 'reason': 'accepted'}\n"
            ),
            tests_changed=("tests/test_vulcan_hardening_score.py",),
            negative_tests_changed=("tests/test_vulcan_hardening_score.py::test_missing_value",),
        )
    )

    assert result.verdict == "PASS"
    assert result.score >= 80
    assert result.production_grade_claim_allowed is True
    assert "fail_closed_behavior_detected" in result.reasons
    assert "negative_tests_changed" in result.reasons


def test_unscoped_runtime_side_effect_blocks():
    side_effect_call = "place_" + "order"
    result = score_hardening(
        HardeningInput(
            changed_files=("core/execution_router.py",),
            patch_text=f"def submit(client):\n    return client.{side_effect_call}()\n",
            tests_changed=("tests/test_execution_router.py",),
            negative_tests_changed=("tests/test_execution_router.py::test_rejects_runtime_path",),
            scoped_runtime_change=False,
        )
    )

    assert result.verdict == "BLOCK"
    assert result.production_grade_claim_allowed is False
    assert "unscoped_runtime_side_effect" in result.blockers
    assert "production_path_side_effect_risk" in result.blockers


def test_score_below_threshold_cannot_claim_production_grade():
    result = score_hardening(
        HardeningInput(
            changed_files=("tools/code_excellence/vulcan/hardening_score.py",),
            patch_text="def helper():\n    return {'reason': 'thin'}\n",
            tests_changed=(),
            negative_tests_changed=(),
        )
    )

    assert result.verdict == "WARN"
    assert result.score < 80
    assert result.production_grade_claim_allowed is False
    assert "negative_tests_absent" in result.reasons


def test_contract_weakening_reduces_score():
    weak_marker = "x" + "fail"
    result = score_hardening(
        HardeningInput(
            changed_files=("tools/code_excellence/vulcan/hardening_score.py",),
            patch_text=f"def test_gate():\n    pytest.{weak_marker}('relax gate')\n",
            tests_changed=("tests/test_vulcan_hardening_score.py",),
            negative_tests_changed=("tests/test_vulcan_hardening_score.py::test_contract",),
            contract_changed=True,
        )
    )

    assert result.verdict == "WARN"
    assert "contract_weakening_risk" in result.reasons
