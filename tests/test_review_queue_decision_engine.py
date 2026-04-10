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
