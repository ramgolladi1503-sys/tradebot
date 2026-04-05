from __future__ import annotations

from config import config as cfg
from core.decision_authority import apply_stage_authority


def test_stage_authority_preserves_builder_rejection_meaning():
    normalized = apply_stage_authority(
        {
            "existing_rejected_at_stage": "trigger",
            "existing_rejection_reason_code": "session_midday_directional_trigger_gate",
            "incoming_rejected_at_stage": None,
            "incoming_rejection_reason_code": "low_selection_probability",
        }
    )

    assert normalized["rejected_at_stage"] == "trigger"
    assert normalized["rejection_reason_code"] == "session_midday_directional_trigger_gate"
    assert normalized["stage_authority_warning"] is True


def test_stage_authority_preserves_risk_rejection_meaning():
    normalized = apply_stage_authority(
        {
            "existing_rejected_at_stage": "risk_budget",
            "existing_rejection_reason_code": "risk_reward_too_low",
            "incoming_rejected_at_stage": None,
            "incoming_rejection_reason_code": "rank_outside_top_n",
        }
    )

    assert normalized["rejected_at_stage"] == "risk_budget"
    assert normalized["rejection_reason_code"] == "risk_reward_too_low"
    assert normalized["stage_authority_warning"] is True


def test_selector_reason_does_not_clobber_prior_stage_without_authority():
    normalized = apply_stage_authority(
        {
            "existing_rejected_at_stage": "entry_quality",
            "existing_rejection_reason_code": "overextended_entry",
            "incoming_rejected_at_stage": None,
            "incoming_rejection_reason_code": "low_selection_probability",
        }
    )

    assert normalized["rejected_at_stage"] == "entry_quality"
    assert normalized["rejection_reason_code"] == "overextended_entry"
    assert normalized["stage_authority_warning"] is True


def test_session_policy_bundle_preserves_existing_defaults():
    midday = cfg.get_session_policy("MIDDAY")
    opening = cfg.get_session_policy("OPENING")

    assert midday["session_mode"] == "MIDDAY"
    assert midday["entry_penalty"] == float(cfg.SESSION_MIDDAY_ENTRY_PENALTY)
    assert midday["directional_trigger_min"] == float(cfg.SESSION_MIDDAY_DIRECTIONAL_TRIGGER_MIN)
    assert opening["entry_penalty"] == float(cfg.SESSION_OPENING_ENTRY_PENALTY)
    assert opening["directional_trigger_min"] is None


def test_regime_policy_bundle_preserves_existing_defaults():
    trending = cfg.get_regime_policy("TRENDING")
    uncertain = cfg.get_regime_policy("UNCERTAIN")

    assert trending["strategy_regime_mode"] == "TRENDING"
    assert trending["family_consensus_min_score"] == float(cfg.FAMILY_CONSENSUS_MIN_SCORE)
    assert uncertain["strategy_regime_mode"] == "UNCERTAIN"
    assert uncertain["family_consensus_min_score"] == float(cfg.FAMILY_CONSENSUS_UNCERTAIN_MIN_SCORE)
