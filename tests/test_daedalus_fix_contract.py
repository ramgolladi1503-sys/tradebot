from __future__ import annotations

from tools.code_excellence.daedalus import DaedalusInput, generate_fix_contract


def _input(**updates):
    payload = {
        "root_cause": "shared fixture drift",
        "confidence": "CONFIRMED",
        "affected_files": ("tests/test_feed_ws.py", "core/kite_depth_ws.py"),
        "proposed_files": ("tests/test_feed_ws.py",),
        "tests_required": ("PYTHONPATH=. pytest tests/test_feed_ws.py -q",),
        "negative_tests_required": ("fixture drift refuses broad runtime patch",),
        "evidence_required": ("agent review evidence",),
        "proof": ("shared_fixture_signal",),
        "regression_risks": ("fixture contract drift",),
        "done_means": ("contract generated",),
    }
    payload.update(updates)
    return DaedalusInput(**payload)


def test_confirmed_root_cause_produces_fix_contract():
    contract = generate_fix_contract(_input())

    assert contract.allowed is True
    assert contract.status == "READY"
    assert contract.reason == "scoped_fix_contract_ready"
    assert contract.decision == "FIX_NOW"
    assert contract.files_to_change == ("tests/test_feed_ws.py",)
    assert "core/kite_depth_ws.py" in contract.files_not_to_touch
    assert contract.negative_tests_required == ("fixture drift refuses broad runtime patch",)
    assert contract.blockers == ()


def test_no_root_cause_refuses_fix_contract():
    contract = generate_fix_contract(_input(root_cause=None, confidence="UNKNOWN", proof=()))

    assert contract.allowed is False
    assert contract.status == "REFUSE"
    assert "root_cause_absent" in contract.blockers
    assert "root_cause_unknown" in contract.blockers
    assert "proof_absent" in contract.blockers


def test_unrelated_file_change_is_blocked():
    contract = generate_fix_contract(_input(proposed_files=("core/unrelated.py",)))

    assert contract.allowed is False
    assert contract.status == "REFUSE"
    assert "unrelated_file_change_blocked" in contract.blockers


def test_absent_negative_tests_make_contract_incomplete():
    contract = generate_fix_contract(_input(negative_tests_required=()))

    assert contract.allowed is False
    assert contract.status == "INCOMPLETE"
    assert contract.blockers == ("negative_tests_required",)


def test_invalid_decision_is_blocked_as_accepted_unknown():
    contract = generate_fix_contract(_input(decision="JUST_MAKE_TESTS_GREEN"))

    assert contract.allowed is False
    assert contract.status == "REFUSE"
    assert contract.decision == "ACCEPTED_UNKNOWN"
    assert "invalid_decision" in contract.blockers
