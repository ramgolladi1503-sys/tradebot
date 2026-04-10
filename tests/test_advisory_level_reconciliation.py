from __future__ import annotations

import pytest

from core import advisory_schema, review_queue
from core.advisory_row_integrity import ADVISORY_ONLY_ROW_KIND, CANONICAL_ROW_KIND


def _canonical_row(**overrides):
    row = {
        "trade_id": "T-LEVEL-1",
        "strategy_id": "CORE",
        "advisory_id": "ADV-LEVEL-1",
        "symbol": "NIFTY",
        "strategy_name": "CORE",
        "timestamp": "2026-03-23T10:00:00+00:00",
        "instrument_type": "OPT",
        "execution_entry": 120.0,
        "execution_entry_source": "ask",
        "execution_entry_status": "executable",
        "display_entry": 120.0,
        "display_entry_source": "ask",
        "display_entry_status": "displayable",
        "entry_reason": "execution_from_ask",
        "entry_clear_reason": None,
        "entry": 120.0,
        "entry_status": "displayable",
        "entry_source": "ask",
        "confidence": 0.7,
        "readiness": "ADVISORY_ONLY",
        "blockers": [],
        "hard_blockers": [],
        "soft_penalties": [],
        "warnings": [],
        "quote_source": "tick_store",
        "quote_age_sec": 1.0,
        "decision_explain": [],
        "market_open": False,
        "side": "BUY",
        "row_kind": CANONICAL_ROW_KIND,
        "stop": 100.0,
        "stop_loss": 100.0,
        "target": 150.0,
        "capital_at_risk": 20.0,
        "rr_ratio": 1.5,
    }
    row.update(overrides)
    return row


def test_locked_final_entry_recomputes_levels_after_late_entry_mutation():
    row = review_queue._lock_final_entry(
        {
            "trade_id": "T-LOCK-1",
            "side": "BUY",
            "entry": 120.0,
            "entry_source": "ask",
            "stop": 100.0,
            "stop_loss": 100.0,
            "target": 150.0,
            "capital_at_risk": 20.0,
            "rr_ratio": 1.5,
            "final_action": "ADVISORY_ONLY",
            "permission": "ADVISORY_ONLY",
            "advisory_visible": True,
        }
    )

    row["entry"] = 141.0
    row["display_entry"] = 141.0
    row["execution_entry"] = 141.0

    reconciled = review_queue._reconcile_locked_final_entry(row)

    assert reconciled["final_entry"] == 120.0
    assert reconciled["entry"] == 120.0
    assert reconciled["display_entry"] == 120.0
    assert reconciled["stop_loss"] == 100.0
    assert reconciled["target"] == 150.0
    assert reconciled["levels_recomputed_from_final_entry"] is True
    assert reconciled["non_canonical_levels"] is False
    assert reconciled["row_kind"] == CANONICAL_ROW_KIND


def test_missing_risk_context_downgrades_locked_row_to_non_canonical():
    row = review_queue._lock_final_entry(
        {
            "trade_id": "T-LOCK-2",
            "side": "BUY",
            "entry": 120.0,
            "entry_source": "ask",
            "final_action": "ADVISORY_ONLY",
            "permission": "ADVISORY_ONLY",
            "advisory_visible": True,
        }
    )

    assert row["final_entry"] == 120.0
    assert row["stop_loss"] is None
    assert row["target"] is None
    assert row["non_canonical_levels"] is True
    assert row["row_kind"] == ADVISORY_ONLY_ROW_KIND
    assert row["level_recompute_reason"] == "insufficient_risk_context"


def test_schema_rejects_canonical_buy_row_with_target_below_entry():
    with pytest.raises(advisory_schema.AdvisorySchemaError, match="BUY invariant failed"):
        advisory_schema.serialize_advisory_row(
            _canonical_row(
                target=110.0,
                stop=100.0,
                stop_loss=100.0,
            )
        )


def test_normalize_trade_levels_converts_mixed_price_space_to_premium():
    row = {
        "trade_id": "T-MIXED-SPACE",
        "symbol": "NIFTY",
        "side": "BUY",
        "execution_entry": 203.75,
        "stop_loss": 23317.287,
        "target": 24269.013,
    }
    out = review_queue._normalize_trade_levels(row)

    assert out["level_space"] == "premium_normalized"
    assert out["level_recompute_reason"] == "mixed_price_spaces"
    assert float(out["stop_loss"]) < float(out["execution_entry"]) < float(out["target"])


def test_apply_level_normalization_promotes_valid_queue_only_candidate():
    row = {
        "trade_id": "T-QUEUE-PROMOTE-LEVEL",
        "symbol": "NIFTY",
        "side": "BUY",
        "candidate_status": "near_executable",
        "execution_status": "scored",
        "candidate_origin": "softened_builder_path",
        "source_flags": {"recoverable_soft_reject": True},
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "execution_blocked": False,
        "hard_blockers": [],
        "unresolved_contract": False,
        "execution_entry": 200.0,
        "stop_loss": 150.0,
        "target": 260.0,
    }
    out = review_queue._apply_level_normalization_and_promotion(row)

    assert out["execution_status"] == "executable"
    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["readiness"] == "READY"
    assert out["execution_entry_status"] == "executable"
    assert out["execution_allowed"] is True


def test_apply_level_normalization_preserves_row_when_levels_missing():
    row = {
        "trade_id": "T-QUEUE-BLOCK-LEVEL",
        "symbol": "NIFTY",
        "side": "BUY",
        "candidate_status": "near_executable",
        "execution_status": "scored",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "execution_blocked": False,
        "hard_blockers": [],
        "unresolved_contract": False,
        "execution_entry": None,
        "display_entry": None,
        "entry": None,
    }
    out = review_queue._apply_level_normalization_and_promotion(row)

    assert out["execution_status"] == "scored"
    assert out["candidate_status"] == "near_executable"
    assert list(out.get("hard_blockers") or []) == []
