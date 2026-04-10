from core import review_queue


def test_recovered_fallback_entry_never_executable():
    entry = {
        "trade_id": "T-FALLBACK-EXEC",
        "symbol": "NIFTY",
        "execution_entry": 125.0,
        "execution_entry_source": "recovered_fallback",
        "execution_entry_status": "executable",
        "display_entry": 125.0,
        "display_entry_source": "recovered_fallback",
        "display_entry_status": "displayable",
        "entry": 125.0,
        "entry_status": "displayable",
        "permission": "EXECUTE",
        "final_action": "EXECUTE",
        "readiness": "READY",
    }
    out = review_queue._enforce_executable_entry_invariant(entry)
    assert out.get("execution_entry_status") == "non_executable"
    out = review_queue._refresh_opportunity_survival_state(out)
    assert out.get("execution_allowed") is False
    assert out.get("execution_status") != "executable"


def test_soft_blocker_confident_candidate_stays_queue_only():
    status, reason = review_queue._compute_execution_decision(
        {
            "symbol": "NIFTY",
            "confidence": 0.71,
            "rank_score": 0.72,
            "blockers": ["latency_guard_cooldown"],
            "hard_blockers": [],
        }
    )
    assert status == "queue_only"
    assert reason == "strong_conf_soft_block_override"


def test_hard_blocker_candidate_stays_blocked():
    status, reason = review_queue._compute_execution_decision(
        {
            "symbol": "NIFTY",
            "confidence": 0.95,
            "rank_score": 0.95,
            "blockers": ["FEED_STALE"],
            "hard_blockers": ["FEED_STALE"],
        }
    )
    assert status == "blocked"
    assert reason == "hard_blocker"


def test_queue_only_entry_keeps_promotable_flag_without_hard_blockers():
    out = review_queue._enforce_executable_entry_invariant(
        {
            "trade_id": "T-QUEUE-PROMOTE-1",
            "symbol": "NIFTY",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "hard_blockers": [],
            "unresolved_contract": False,
        }
    )

    assert out["execution_status"] == "queue_only"
    assert out["is_executable"] is False
    assert out["eligible_for_execution"] is True


def test_queue_only_entry_with_unresolved_contract_not_promotable():
    out = review_queue._enforce_executable_entry_invariant(
        {
            "trade_id": "T-QUEUE-PROMOTE-2",
            "symbol": "NIFTY",
            "permission": "QUEUE_ONLY",
            "final_action": "QUEUE_ONLY",
            "readiness": "QUEUE_ONLY",
            "execution_status": "queue_only",
            "hard_blockers": [],
            "unresolved_contract": True,
        }
    )

    assert out["execution_status"] == "queue_only"
    assert out["is_executable"] is False
    assert not bool(out.get("eligible_for_execution"))


def test_review_queue_respects_decision_engine_queue_for_weak_signal():
    entry = {
        "trade_id": "T-RQ-WEAK",
        "symbol": "NIFTY",
        "candidate_status": "near_executable",
        "candidate_class": "softened",
        "execution_status": "queue_only",
        "permission": "QUEUE_ONLY",
        "final_action": "QUEUE_ONLY",
        "readiness": "QUEUE_ONLY",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "display_entry": 150.0,
        "display_entry_status": "displayable",
        "entry": 150.0,
        "entry_status": "displayable",
        "stop_loss": 120.0,
        "target": 210.0,
        "hard_blockers": [],
        "blockers": [],
        "source_flags": {"soft_reject_reason": "weak_signal"},
        "quote_source": "tick_store",
        "quote_validation_status": "OK",
        "quote_age_sec": 0.5,
        "spread_pct": 0.003,
        "volume": 5000,
        "builder_confidence": 0.82,
        "gating_final_confidence": 0.85,
        "rank_score": 0.80,
        "confidence_final": 0.85,
        "regime": "TREND",
        "side": "BUY",
        "strategy_family": "ensemble_opt",
        "tradable": True,
    }

    out = review_queue._maybe_promote_execute_candidate(entry)
    assert out["permission"] == "QUEUE_ONLY"
    assert out["final_action"] == "QUEUE_ONLY"
    assert out["execution_status"] in {"queue_only", "advisory_only"}
    assert out.get("promotion_block_reason") == "soft_reject_weak_signal_blocks_execute"
