from __future__ import annotations

import json
from pathlib import Path

from scripts.check_prospective_structural_edge_lockbox_readiness import build_readiness
from scripts.update_prospective_structural_edge_lockbox import SAFETY_FLAGS


BASE = Path("research/prospective_structural_edge_v2")


def _load(name: str) -> dict:
    return json.loads((BASE / name).read_text())


def test_prior_epoch_closed_and_old_lockbox_not_reusable():
    audit = _load("prior_epoch_closure_audit.json")
    disposition = _load("old_lockbox_disposition.json")

    assert audit["prior_epoch_closed"] is True
    assert audit["required_conclusion"]["OLD_LOCKBOX_REUSABLE"] == "NO"
    assert disposition["OLD_LOCKBOX_STATUS"] == "OPENED_ONCE_AND_EXHAUSTED"
    assert disposition["old_lockbox_reused"] is False
    assert "AC07_MIDDAY_COMPRESSION_LATE_EXPANSION" in disposition["prohibited_retests"]
    assert "AC08_VWAP_INVENTORY_TRANSFER" in disposition["prohibited_retests"]


def test_prospective_manifest_is_outcome_blind_and_post_old_epoch_only():
    manifest = _load("prospective_session_manifest.json")

    assert manifest["after_session"] == "20260710"
    assert manifest["prospective_outcomes_inspected"] is False
    assert all(session["session"] > "20260710" for session in manifest["sessions"])
    assert not any(session["eligibility_status"] == "ELIGIBLE_PROSPECTIVE_SESSION" for session in manifest["sessions"])


def test_seal_gates_require_80_sessions_and_120_days():
    readiness = build_readiness(
        {
            "epoch_id": "PROSPECTIVE_STRUCTURAL_EDGE_EPOCH_V2",
            "sessions": [
                {"session": "20260713", "eligibility_status": "ELIGIBLE_PROSPECTIVE_SESSION"},
                {"session": "20260714", "eligibility_status": "ELIGIBLE_PROSPECTIVE_SESSION"},
            ],
        }
    )

    assert readiness["lockbox_seal_status"] == "NOT_READY"
    assert "INSUFFICIENT_ELIGIBLE_SESSIONS" in readiness["blockers"]
    assert "INSUFFICIENT_CALENDAR_SPAN" in readiness["blockers"]
    assert readiness["prospective_outcomes_inspected"] is False


def test_alpha_is_carried_forward_not_reset():
    alpha = _load("alpha_spending_ledger.json")

    assert alpha["prior_alpha_assigned"]["AC07_MIDDAY_COMPRESSION_LATE_EXPANSION"] == 0.025
    assert alpha["prior_alpha_assigned"]["AC08_VWAP_INVENTORY_TRANSFER"] == 0.015
    assert alpha["remaining_project_alpha"] == 0.01
    assert alpha["alpha_reset"] is False


def test_safety_flags_are_fail_closed():
    for name in [
        "prospective_epoch_contract.json",
        "prospective_lockbox_contract.json",
        "cumulative_hypothesis_ledger.json",
        "alpha_spending_ledger.json",
    ]:
        artifact = _load(name)
        assert artifact["safety_flags"] == SAFETY_FLAGS
