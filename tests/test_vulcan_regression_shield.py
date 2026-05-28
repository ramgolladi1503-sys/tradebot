from __future__ import annotations

from tools.code_excellence.vulcan import PROTECTED_CONTRACTS, RegressionShieldInput, evaluate_regression_shield


def _complete_contracts(**updates):
    contracts = dict(PROTECTED_CONTRACTS)
    contracts.update(updates)
    return contracts


def test_weakened_fallback_rejection_blocks():
    contracts = _complete_contracts(fallback_non_executable_policy=("reject_non_executable",))

    report = evaluate_regression_shield(RegressionShieldInput(current_contracts=contracts))

    assert report.verdict == "BLOCK"
    assert report.allowed is False
    assert "fallback_non_executable_policy" in report.weakened_contracts
    assert "fallback_non_executable_policy_weakened" in report.blockers


def test_removed_required_evidence_field_blocks():
    contracts = _complete_contracts(non_action_evidence=("is_order_action=false",))

    report = evaluate_regression_shield(RegressionShieldInput(current_contracts=contracts))

    assert report.verdict == "BLOCK"
    assert "non_action_evidence" in report.weakened_contracts
    assert "non_action_evidence_weakened" in report.blockers


def test_removed_or_weakened_tests_block():
    weak_marker = "x" + "fail"
    report = evaluate_regression_shield(
        RegressionShieldInput(
            current_contracts=_complete_contracts(),
            patch_text=f"def test_contract():\n    pytest.{weak_marker}('relax gate')\n",
            removed_tests=("tests/test_existing_contract.py",),
        )
    )

    assert report.verdict == "BLOCK"
    assert "test_weakening" in report.weakened_contracts
    assert "tests_weakened" in report.blockers


def test_clean_protected_contracts_pass():
    report = evaluate_regression_shield(RegressionShieldInput(current_contracts=_complete_contracts()))

    assert report.verdict == "PASS"
    assert report.allowed is True
    assert report.weakened_contracts == ()
    assert report.blockers == ()
    assert set(report.protected_contracts) == set(PROTECTED_CONTRACTS)
