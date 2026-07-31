from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

import pytest

from config import config as cfg
from core import approval_store
from core.execution_guard import ExecutionGuard
from core.opportunity_engine import annotate_ranked_opportunities, select_top_opportunities
from core.trade_schema import Trade


pytestmark = [
    pytest.mark.behavior,
    pytest.mark.safety,
    pytest.mark.regression,
    pytest.mark.edge,
]


def _trade(
    *,
    trade_id: str,
    confidence: float = 0.72,
    bid: float = 120.0,
    ask: float = 120.5,
    ltp: float = 120.2,
    quote_age_sec: float = 0.2,
    volume: float = 10_000,
    execution_allowed: bool = True,
    tradable: bool = True,
    execution_entry: float | None = 120.5,
    execution_entry_status: str = "executable",
    display_entry: float | None = 120.5,
    source_flags: dict | None = None,
    row_kind: str | None = None,
) -> Trade:
    flags = {
        "last_tick_age_sec": quote_age_sec,
        "last_depth_age_sec": quote_age_sec,
        "subscribed_option_tokens_count": 1,
        "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
        "option_last_tick_age_by_symbol": {"NIFTY": quote_age_sec},
        "symbol_feed_ok_by_symbol": {"NIFTY": True},
        "quote_source": "LIVE_WS",
        "liquidity_source": "LIVE_DEPTH",
    }
    flags.update(source_flags or {})
    trade = Trade(
        trade_id=trade_id,
        timestamp=datetime(2026, 7, 31, 10, 0, 0),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=12345,
        strike=25000,
        expiry="2026-08-04",
        side="BUY",
        entry_price=120.5,
        stop_loss=112.0,
        target=138.0,
        qty=1,
        capital_at_risk=8.5,
        expected_slippage=0.2,
        confidence=confidence,
        strategy="UNIT_TREND",
        regime="TREND",
        builder_confidence=confidence,
        permission_confidence=max(0.0, confidence - 0.02),
        gating_final_confidence=max(0.0, confidence - 0.03),
        confidence_raw_canonical=confidence,
        sizing_confluence_score=confidence,
        volume=volume,
        current_volume=volume,
        quote_age_sec=quote_age_sec,
        execution_allowed=execution_allowed,
        tradable=tradable,
        execution_ok=True,
        execution_entry=execution_entry,
        execution_entry_status=execution_entry_status,
        execution_entry_source="ask" if execution_entry is not None else "none",
        display_entry=display_entry,
        display_entry_status="displayable" if display_entry is not None else "missing",
        display_entry_source="ask" if display_entry is not None else "none",
        expected_entry=display_entry,
        expected_entry_source="ask" if display_entry is not None else "none",
        opt_bid=bid,
        opt_ask=ask,
        best_bid=bid,
        best_ask=ask,
        opt_ltp=ltp,
        current_ltp=ltp,
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        source_flags=flags,
        tradingsymbol="NIFTY2680425000CE",
        instrument_id="NIFTY|2026-08-04|25000|CE",
        reason="qa_whole_tradebot",
    )
    if row_kind is not None:
        object.__setattr__(trade, "row_kind", row_kind)
    return trade


@pytest.mark.broker_firewall
def test_fallback_truth_cannot_receive_execution_selection_or_capital():
    fallback = _trade(
        trade_id="fallback",
        confidence=0.99,
        source_flags={
            "recovered_fallback": True,
            "fallback_candidate": True,
            "candidate_origin": "fallback",
            "quote_source": "REST_RECOVERY",
        },
        row_kind="recovered_fallback",
    )

    ranked = annotate_ranked_opportunities([fallback], scope="unit:allocator", top_n=1)
    row = ranked[0]

    assert row.candidate_class == "ADVISORY_ONLY"
    assert row.execution_allowed is False
    assert row.selected_for_execution is False
    assert row.truth_allows_execution is False
    assert row.slot_id is None
    assert row.capital_assigned is None
    assert row.selection_reason in {
        "not_execution_eligible",
        "execution_truth_blocked",
        "portfolio_not_selected",
    }


def test_ranking_separates_real_quality_instead_of_echoing_input_order():
    weak = _trade(
        trade_id="weak",
        confidence=0.46,
        bid=120.0,
        ask=121.8,
        ltp=120.8,
        quote_age_sec=1.4,
        volume=1_000,
    )
    strong = _trade(
        trade_id="strong",
        confidence=0.86,
        bid=120.0,
        ask=120.2,
        ltp=120.1,
        quote_age_sec=0.1,
        volume=25_000,
    )

    ranked = annotate_ranked_opportunities([weak, strong], scope="unit:main", top_n=1)

    assert [item.trade_id for item in ranked] == ["strong", "weak"]
    assert ranked[0].priority_score > ranked[1].priority_score
    assert ranked[0].rank_score > ranked[1].rank_score
    assert ranked[0].selected_for_execution is True
    assert ranked[1].selected_for_execution is False


@pytest.mark.replay
def test_ranked_candidate_replay_is_deterministic_and_does_not_mutate_input():
    original = [
        _trade(trade_id="replay-weak", confidence=0.51, bid=120.0, ask=121.5, volume=900),
        _trade(trade_id="replay-strong", confidence=0.84, bid=120.0, ask=120.2, volume=22_000),
    ]
    frozen_before = [item.to_dict() for item in original]

    first = annotate_ranked_opportunities(deepcopy(original), scope="replay:deterministic", top_n=1)
    second = annotate_ranked_opportunities(deepcopy(original), scope="replay:deterministic", top_n=1)

    assert [item.to_dict() for item in first] == [item.to_dict() for item in second]
    assert [item.trade_id for item in first] == ["replay-strong", "replay-weak"]
    assert [item.to_dict() for item in original] == frozen_before


@pytest.mark.chaos
def test_late_risk_revalidation_overrides_prior_top_rank(monkeypatch):
    trade = _trade(trade_id="ranked-then-risk-blocked", confidence=0.90)
    ranked = annotate_ranked_opportunities([trade], scope="unit:main", top_n=1)
    assert ranked[0].selected_for_execution is True

    class RejectingRiskState:
        def approve(self, candidate):
            return False, "daily_loss_limit"

    class PassingSurvivalGates:
        def evaluate(self, **kwargs):
            return SimpleNamespace(allowed_entries=True, size_multiplier=1.0, context={})

    monkeypatch.setattr(cfg, "REGIME_MONITOR_ENABLED", False, raising=False)
    guard = ExecutionGuard(
        risk_state=RejectingRiskState(),
        survival_gates=PassingSurvivalGates(),
    )

    decision = guard.evaluate(
        ranked[0],
        {"capital": 100_000},
        "TREND",
        market_data={"execution_mode": "PAPER", "market_open": True},
        mode="PAPER",
    )

    assert decision.allowed is False
    assert decision.reason.startswith("RiskState:")
    assert "daily_loss_limit" in decision.reason


@pytest.mark.broker_firewall
def test_order_approval_is_consumed_exactly_once(tmp_path, monkeypatch):
    db_path = tmp_path / "tradebot.sqlite"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    monkeypatch.setattr(approval_store, "append_event", lambda payload: None)

    created, created_reason = approval_store.create_order_approval(
        order_intent_hash="intent-123",
        approver_id="qa",
        status="APPROVED",
        ttl_sec=60,
        now_epoch=1_000.0,
    )
    first = approval_store.consume_valid_approval(
        "intent-123",
        approver_id="qa",
        now_epoch=1_001.0,
        require_armed=False,
    )
    second = approval_store.consume_valid_approval(
        "intent-123",
        approver_id="qa",
        now_epoch=1_002.0,
        require_armed=False,
    )

    assert created is True
    assert created_reason == "approved"
    assert first == (True, "approved_and_used")
    assert second == (False, "approval_used")


@pytest.mark.ui_read_model
@pytest.mark.broker_firewall
def test_operator_pools_never_present_fallback_as_executable():
    real = _trade(trade_id="real", confidence=0.80)
    fallback = _trade(
        trade_id="fallback-ui",
        confidence=0.99,
        source_flags={
            "recovered_fallback": True,
            "candidate_origin": "fallback",
            "quote_source": "REST_RECOVERY",
        },
        row_kind="recovered_fallback",
    )

    pools = select_top_opportunities(
        [fallback, real],
        executable_top_n=5,
        advisory_top_n=5,
    )
    executable_ids = [item.trade_id for item in pools["top_executable_opportunities"]]
    advisory_ids = [item.trade_id for item in pools["top_advisory_opportunities"]]

    assert executable_ids == ["real"]
    assert "fallback-ui" in advisory_ids
    assert set(executable_ids).isdisjoint(advisory_ids)
