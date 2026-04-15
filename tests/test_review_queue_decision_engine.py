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
