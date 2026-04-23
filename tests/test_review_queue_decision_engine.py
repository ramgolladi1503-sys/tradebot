import pytest

from config import config as cfg
from core import review_queue


def _candidate(**overrides):
    row = {
        "trade_id": "T-DECISION-ENGINE",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "execution_status": "queue_only",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "display_entry": 150.0,
        "display_entry_status": "displayable",
        "entry": 150.0,
        "entry_status": "displayable",
        "tradable": True,
        "execution_allowed": True,
        "hard_blockers": [],
        "blockers": [],
        "confidence_final": 0.82,
        "gating_final_confidence": 0.82,
        "selected_for_execution": True,
        "rank_global": 1,
        "quote_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_age_sec": 0.5,
        "best_bid": 149.8,
        "best_ask": 150.2,
        "opt_ltp": 150.0,
        "current_ltp": 150.0,
        "spread_pct": 0.002666,
        "volume": 10000,
        "liquidity_score": 0.8,
        "execution_ok": True,
        "data_state": "DATA_LIVE",
    }
    row.update(overrides)
    return row


def test_weak_signal_candidate_never_promotes_to_execute(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_CONF", 0.72, raising=False)
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)

    out = review_queue._maybe_promote_execute_candidate(
        _candidate(reject_reason="weak_signal", raw_rank_score=0.72)
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out.get("promotion_block_reason") == "weak_signal_queue_only"


def test_low_raw_rank_candidate_never_promotes_even_if_final_confidence_high(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_CONF", 0.72, raising=False)
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)

    out = review_queue._maybe_promote_execute_candidate(
        _candidate(raw_rank_score=0.18, rank_score=0.66)
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out.get("promotion_block_reason") == "raw_rank_below_execute_floor"


def test_clean_strong_candidate_promotes_to_execute(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_CONF", 0.72, raising=False)
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)

    out = review_queue._maybe_promote_execute_candidate(
        _candidate(
            trade_id="T-STRONG-EXEC",
            strategy_family="ensemble_opt",
            raw_rank_score=0.58,
            rank_score=0.68,
        )
    )

    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["execution_status"] == "executable"


def test_finalize_append_payload_requires_precomputed_terminal_score(monkeypatch):
    calls = {"count": 0}

    def _boom(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("emit path must not rescore payloads")

    monkeypatch.setattr(review_queue, "score_candidate", _boom)

    payload = _candidate(
        trade_id="T-APPEND-READY",
        strategy_family="breakout",
        candidate_status="executable",
        confidence=0.71,
        rank_score=0.64,
        terminal_scoring_applied=True,
    )

    out = review_queue._finalize_append_payload_for_runtime_write(payload)

    assert out["rank_score"] == 0.64
    assert out["terminal_scoring_applied"] is True
    assert calls["count"] == 0


def test_finalize_append_payload_rejects_unscored_payload():
    with pytest.raises(AssertionError, match="terminal scoring not applied at emit"):
        review_queue._finalize_append_payload_for_runtime_write(
            _candidate(
                trade_id="T-APPEND-MISSING-SCORE",
                strategy_family="breakout",
                rank_score=None,
                terminal_scoring_applied=False,
            )
        )


def test_finalize_append_payload_allows_diagnostic_payload_without_terminal_score(monkeypatch):
    calls = {"count": 0}

    def _boom(*args, **kwargs):
        calls["count"] += 1
        raise AssertionError("diagnostic payload must not be rescored")

    monkeypatch.setattr(review_queue, "score_candidate", _boom)

    payload = _candidate(
        trade_id="T-DIAGNOSTIC-APPEND",
        strategy_family="breakout",
        candidate_status="blocked",
        confidence=None,
        rank_score=None,
        terminal_scoring_applied=False,
        final_action="BLOCK",
        permission="BLOCK",
        readiness="BLOCKED",
        execution_status="blocked",
        hard_blockers=[],
        blockers=[],
        final_emit_block_reason="missing_execution_entry",
    )

    out = review_queue._finalize_append_payload_for_runtime_write(
        payload,
        require_terminal_scoring=False,
        require_ranked_candidate_ready=False,
    )

    assert out["final_emit_block_reason"] == "missing_execution_entry"
    assert out["terminal_scoring_applied"] is False
    assert calls["count"] == 0


def test_blocked_advisory_rows_backfill_hard_blockers_before_serialization():
    payload = _candidate(
        trade_id="T-BLOCKED-ADVISORY",
        strategy_id="S-BLOCKED-ADVISORY",
        strategy_name="Breakout",
        advisory_id="A-BLOCKED-ADVISORY",
        strategy_family="breakout",
        candidate_status="blocked",
        confidence=0.31,
        rank_score=0.22,
        terminal_scoring_applied=True,
        final_action="BLOCK",
        permission="BLOCK",
        readiness="BLOCKED",
        execution_status="blocked",
        hard_blockers=[],
        blockers=[],
        final_emit_block_reason="missing_execution_entry",
        entry_block_code=None,
        hard_reason=None,
        final_blocker=None,
        execution_block_reason=None,
        instrument_type="OPT",
    )

    out = review_queue._ensure_blocked_advisory_hard_blockers(payload)

    assert "missing_execution_entry" in list(out["hard_blockers"] or [])
    assert "missing_execution_entry" in list(out["blockers"] or [])
    serialized = review_queue.serialize_advisory_row(out, allow_legacy=True)
    assert "missing_execution_entry" in list(serialized["hard_blockers"] or [])


def test_queue_only_backdoor_promotion_blocked_by_raw_rank_floor(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)
    out = review_queue._promote_queue_only_candidate(
        {
            "trade_id": "tbsoft_NIFTY_1",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_entry": 150.0,
            "execution_entry_status": "executable",
            "display_entry": 150.0,
            "entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
            "tradable": True,
            "execution_allowed": True,
            "execution_ok": True,
            "execution_blocked": False,
            "hard_blockers": [],
            "unresolved_contract": False,
            "source_flags": {"recoverable_soft_reject": True},
            "raw_rank_score": 0.18,
            "rank_score": 0.72,
        }
    )
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out["promotion_block_reason"] == "raw_rank_below_execute_floor"


def test_queue_only_backdoor_promotion_blocked_for_weak_signal(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)
    out = review_queue._promote_queue_only_candidate(
        {
            "trade_id": "tbsoft_NIFTY_2",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_entry": 150.0,
            "execution_entry_status": "executable",
            "display_entry": 150.0,
            "entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
            "tradable": True,
            "execution_allowed": True,
            "execution_ok": True,
            "execution_blocked": False,
            "hard_blockers": [],
            "unresolved_contract": False,
            "source_flags": {
                "recoverable_soft_reject": True,
                "soft_reject_reason": "weak_signal",
            },
            "raw_rank_score": 0.50,
            "rank_score": 0.72,
            "gating_final_confidence": 0.82,
            "quote_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "best_bid": 149.8,
            "best_ask": 150.2,
            "opt_ltp": 150.0,
            "current_ltp": 150.0,
            "spread_pct": 0.002666,
            "volume": 10000,
            "liquidity_score": 0.8,
            "data_state": "DATA_LIVE",
            "selected_for_execution": True,
            "rank_global": 1,
        }
    )
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out["promotion_block_reason"] == "weak_signal_queue_only"


def test_queue_only_normalization_path_delegates_to_decision_engine(monkeypatch):
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_MIN_RAW_RANK", 0.35, raising=False)
    calls = {"count": 0}

    def _stub_maybe_promote(entry):
        calls["count"] += 1
        out = dict(entry)
        out["promotion_block_reason"] = "decision_engine_reject"
        return out

    monkeypatch.setattr(review_queue, "_maybe_promote_execute_candidate", _stub_maybe_promote)

    out = review_queue._promote_queue_only_candidate(
        {
            "trade_id": "tbsoft_NIFTY_3",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_entry": 150.0,
            "execution_entry_status": "executable",
            "display_entry": 150.0,
            "entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
            "tradable": True,
            "execution_allowed": True,
            "execution_ok": True,
            "execution_blocked": False,
            "hard_blockers": [],
            "unresolved_contract": False,
            "source_flags": {"recoverable_soft_reject": True},
            "quote_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "raw_rank_score": 0.50,
            "rank_score": 0.72,
            "gating_final_confidence": 0.82,
            "selected_for_execution": True,
        }
    )

    assert calls["count"] == 1
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out.get("promotion_candidate") == "post_level_normalization"
    assert out["promotion_block_reason"] == "decision_engine_reject"


def test_level_normalization_does_not_promote_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    monkeypatch.setattr(cfg, "PERMISSION_PROMOTION_ENABLE", True, raising=False)

    out = review_queue._apply_level_normalization_and_promotion(
        {
            "trade_id": "tbsoft_NIFTY_STRICT",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_entry": 150.0,
            "execution_entry_status": "executable",
            "display_entry": 150.0,
            "entry": 150.0,
            "stop_loss": 120.0,
            "target": 210.0,
            "tradable": True,
            "execution_allowed": True,
            "execution_ok": True,
            "execution_blocked": False,
            "hard_blockers": [],
            "unresolved_contract": False,
            "source_flags": {"recoverable_soft_reject": True},
            "quote_source": "tick_store",
            "quote_validation_status": "OK",
            "quote_age_sec": 0.5,
            "raw_rank_score": 0.80,
            "rank_score": 0.80,
            "gating_final_confidence": 0.85,
            "selected_for_execution": True,
        }
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out.get("promotion_candidate") is None


def test_enforce_non_executable_emit_lifecycle_clamps_execute_fields():
    out = review_queue._enforce_non_executable_emit_lifecycle(
        {
            "trade_id": "T-EMIT-CLAMP",
            "symbol": "NIFTY",
            "candidate_status": "advisory_only",
            "execution_status": "advisory_only",
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "readiness": "READY",
            "execution_entry": None,
            "execution_entry_status": "non_executable",
            "execution_allowed": False,
            "eligible_for_execution": False,
            "tradable": True,
            "is_executable": True,
        }
    )

    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["readiness"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out["execution_allowed"] is False
    assert out["eligible_for_execution"] is False


def test_enforce_non_executable_emit_lifecycle_leaves_eligible_row_unchanged():
    row = {
        "trade_id": "T-EMIT-EXEC",
        "symbol": "NIFTY",
        "candidate_status": "executable",
        "execution_status": "executable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_allowed": True,
        "eligible_for_execution": True,
        "tradable": True,
        "is_executable": True,
    }
    out = review_queue._enforce_non_executable_emit_lifecycle(row)
    assert out["permission"] == "EXECUTE"
    assert out["final_action"] == "EXECUTE"
    assert out["execution_status"] == "executable"
    assert out["execution_allowed"] is True


def test_is_execution_eligible_accepts_execute_intent_when_status_lags():
    row = {
        "trade_id": "T-EXEC-INTENT-LAG",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "instrument": "OPT",
        "tradingsymbol": "NIFTY2642124300CE",
        "expiry_date": "2026-04-21",
        "option_type": "CE",
        "instrument_token": 12345,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "candidate_status": "near_executable",
        "execution_status": "advisory_only",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "execution_allowed": True,
        "execution_blocked": False,
        "unresolved_contract": False,
        "hard_blockers": [],
        "blockers": [],
    }
    assert review_queue._is_execution_eligible(row) is True


def test_is_execution_eligible_rejects_execute_intent_with_hard_blocker():
    row = {
        "trade_id": "T-EXEC-INTENT-BLOCKED",
        "symbol": "NIFTY",
        "strategy_family": "breakout",
        "instrument": "OPT",
        "tradingsymbol": "NIFTY2642124300CE",
        "expiry_date": "2026-04-21",
        "option_type": "CE",
        "instrument_token": 12345,
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
        "candidate_status": "near_executable",
        "execution_status": "advisory_only",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_entry_source": "ask",
        "execution_allowed": True,
        "execution_blocked": False,
        "unresolved_contract": False,
        "hard_blockers": ["NO_LIVE_OPTION_FEED"],
        "blockers": ["NO_LIVE_OPTION_FEED"],
    }
    assert review_queue._is_execution_eligible(row) is False


def test_execution_ineligibility_reason_prefers_specific_blocker():
    row = {
        "trade_id": "T-INELIGIBLE-REASON",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "execution_status": "queue_only",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_block_reason": "execution_quality_reject",
    }
    assert review_queue._execution_ineligibility_reason(row) == "execution_quality_reject"


def test_execution_ineligibility_reason_prefers_stale_quote_validation_status_over_contract_symptom():
    row = {
        "trade_id": "T-INELIGIBLE-STALE",
        "symbol": "NIFTY",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "execution_status": "queue_only",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "execution_allowed": False,
        "eligible_for_execution": False,
        "unresolved_contract": True,
        "quote_validation_status": "STALE_OPTION_LTP",
        "hard_blockers": [],
        "blockers": [],
    }
    assert review_queue._execution_ineligibility_reason(row) == "STALE_OPTION_LTP"


def test_enforce_non_executable_emit_lifecycle_preserves_specific_reason_and_avoids_near_executable():
    out = review_queue._enforce_non_executable_emit_lifecycle(
        {
            "trade_id": "T-EMIT-REASON",
            "symbol": "NIFTY",
            "candidate_status": "near_executable",
            "execution_status": "queue_only",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_entry": 150.0,
            "execution_entry_status": "executable",
            "execution_allowed": True,
            "eligible_for_execution": False,
            "tradable": True,
            "rank_score": 0.78,
            "execution_block_reason": "execution_quality_reject",
        }
    )
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] == "queue_only"
    assert out["candidate_status"] == "advisory_only"
    assert out["final_emit_block_reason"] == "execution_quality_reject"
    assert out["permission_reason"] == "execution_quality_reject"


def test_issue_classification_softens_minor_price_mismatch_for_execute_intent():
    row = {
        "trade_id": "T-MISMATCH-SOFT",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "permission": "EXECUTE",
        "quote_source": "tick_store",
        "quote_validation_status": "PRICE_MISMATCH",
        "execution_entry": 100.0,
        "validation_reference_price": 101.5,
        "current_ltp": 100.0,
        "market_open": True,
        "blockers": [],
        "hard_blockers": [],
    }
    out = review_queue._apply_issue_classification(
        row,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
    )
    assert "PRICE_MISMATCH" in list(out.get("soft_penalties") or [])
    assert "PRICE_MISMATCH" not in list(out.get("hard_blockers") or [])


def test_issue_classification_keeps_severe_price_mismatch_hard():
    row = {
        "trade_id": "T-MISMATCH-HARD",
        "symbol": "NIFTY",
        "instrument": "OPT",
        "permission": "EXECUTE",
        "quote_source": "tick_store",
        "quote_validation_status": "PRICE_MISMATCH",
        "execution_entry": 100.0,
        "validation_reference_price": 140.0,
        "current_ltp": 100.0,
        "quote_age_sec": 0.5,
        "market_open": True,
        "blockers": [],
        "hard_blockers": [],
    }
    out = review_queue._apply_issue_classification(
        row,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
    )
    assert "PRICE_MISMATCH" in list(out.get("hard_blockers") or [])


def test_terminal_scoring_is_idempotent_and_bounded(monkeypatch):
    monkeypatch.setattr(cfg, "TERMINAL_SCORING_MAX_ABS_DELTA", 0.15, raising=False)
    monkeypatch.setattr(cfg, "TERMINAL_SCORING_MAX_MULT", 1.35, raising=False)

    calls = {"count": 0}

    def _fake_score_candidate(candidate, market_data, context):
        calls["count"] += 1
        return {
            "rank_score": 0.90,
            "opportunity_score": 0.90,
            "confidence_raw": 0.90,
            "confidence_final": 0.90,
            "score_breakdown": {},
            "penalty_reasons": [],
            "score_inputs_used": {},
            "confluence_score": 0.90,
            "setup_strength": 0.90,
            "regime_fit": 0.90,
            "liquidity_score": 0.90,
            "spread_score": 0.90,
            "rr_score": 0.90,
            "timing_score": 0.90,
            "penalty_score": 0.0,
        }

    monkeypatch.setattr(review_queue, "score_candidate", _fake_score_candidate)

    row = {
        "trade_id": "T-TERM-BOUNDED",
        "symbol": "NIFTY",
        "strategy_family": "ensemble_opt",
        "candidate_type": "directional",
        "rank_score": 0.18,
        "raw_rank_score": 0.18,
    }
    out1 = review_queue._apply_terminal_candidate_scoring(
        row,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
        market_open_for_entry=True,
    )
    out2 = review_queue._apply_terminal_candidate_scoring(
        out1,
        mode_for_entry="LIVE",
        allow_stale_quotes_for_entry=False,
        market_open_for_entry=True,
    )

    assert round(float(out1["rank_score"]), 6) == 0.33
    assert out1["terminal_scoring_applied"] is True
    assert float(out2["rank_score"]) == float(out1["rank_score"])
    assert calls["count"] == 2
