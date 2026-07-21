from __future__ import annotations

import json
from pathlib import Path

from research.independent_underlying_evaluation_v3 import evaluate_ac16, evaluate_ac24


BASE = Path("research/independent_underlying_evaluation_v3")


def test_pre_open_integrity_passed_before_open():
    report = json.loads((BASE / "pre_open_seal_verification.json").read_text())
    assert report["verdict"] == "PASS"
    assert report["external_hash_audit"] == "PASS"
    assert report["session_count"] == 366
    assert report["opened"] is False


def test_frozen_candidate_hashes_are_hardcoded():
    assert evaluate_ac24.SPECIFICATION_HASH == "81137922979a0497e16616ca0c596197c72b4ce1e28dfb153e81829f55f2934b"
    assert evaluate_ac16.PARAMETER_HASH == "96962f33f660a0f6927b860b475ac2c595bc62cd7e156e9ad6bfc1816052bc98"


def test_statistical_contract_forbids_overrides_and_alpha_reassignment():
    contract = json.loads((BASE / "independent_evaluation_statistical_contract.json").read_text())
    assert contract["candidate_order"] == [evaluate_ac24.HYPOTHESIS_ID, evaluate_ac16.HYPOTHESIS_ID]
    assert contract["unused_alpha_reassignment_allowed"] is False
    assert contract["option_data_required"] is False
    assert contract["execution_eligibility"] is False

