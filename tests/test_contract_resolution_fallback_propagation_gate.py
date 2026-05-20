from __future__ import annotations

from datetime import datetime

from core.candidate_finalization import mirror_candidate_truth
from core.trade_schema import Trade
from strategies.trade_builder import TradeBuilder


def _trade(**overrides):
    base = dict(
        trade_id="t1",
        timestamp=datetime.now(),
        symbol="NIFTY",
        instrument="OPT",
        instrument_type="OPT",
        instrument_token=123,
        strike=23650,
        expiry="2026-05-26",
        side="BUY",
        entry_price=100.0,
        stop_loss=80.0,
        target=130.0,
        qty=1,
        capital_at_risk=20.0,
        expected_slippage=0.0,
        confidence=0.7,
        strategy="test",
        regime="TEST",
        right="CE",
        option_type="CE",
        tradingsymbol="NIFTY26MAY23650CE",
        instrument_id="NIFTY|2026-05-26|23650|CE",
        execution_allowed=True,
        selected_for_execution=True,
        tradable=True,
        permission="EXECUTE",
        final_action="EXECUTE",
        readiness="READY",
        execution_status="executable",
        execution_entry=101.0,
        execution_entry_status="executable",
        candidate_status="executable",
        strategy_family="continuation",
        rank_score=0.8,
    )
    base.update(overrides)
    return Trade(**base)


def test_mirror_candidate_truth_blocks_contract_resolution_fallback():
    trade = _trade()
    out = mirror_candidate_truth(
        trade,
        decision_trace={
            "permission": "EXECUTE",
            "final_action": "EXECUTE",
            "execution_allowed": True,
            "execution_entry_status": "executable",
            "candidate_status": "executable",
        },
        lifecycle={"execution_entry": 101.0, "execution_entry_status": "executable"},
        contract_resolution={
            "requested_strike": 23750,
            "resolved_strike": 23650,
            "requested_expiry": "2026-05-26",
            "resolved_expiry": "2026-05-26",
            "contract_exact_match": False,
            "resolution_mode": "fallback",
            "fallback_used": True,
            "fallback_reason": "nearest_contract_match",
            "fallback_execution_policy": "QUEUE_ONLY",
        },
        fallback_metadata={
            "fallback_used": True,
            "fallback_reason": "nearest_contract_match",
        },
    )

    assert out.execution_allowed is False
    assert out.selected_for_execution is False
    assert out.tradable is False
    assert out.permission == "QUEUE_ONLY"
    assert out.final_action == "QUEUE_ONLY"
    assert out.execution_status == "queue_only"
    assert out.execution_entry is None
    assert out.execution_entry_status == "blocked_contract"
    assert out.candidate_status == "advisory_only"
    assert out.source_flags["contract_resolution_fallback_used"] is True


def test_option_tradability_precondition_rejects_fallback_contract(monkeypatch):
    builder = TradeBuilder(predictor=object())
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda *args, **kwargs: {
            "expiry": "2026-05-26",
            "tradingsymbol": "NIFTY26MAY23650CE",
            "instrument_token": 123,
            "instrument_id": "NIFTY|2026-05-26|23650|CE",
            "fallback_applied": True,
        },
    )

    ok, payload = builder._option_tradability_precondition(
        symbol="NIFTY",
        opt={
            "strike": 23750,
            "type": "CE",
            "ltp": 100.0,
            "bid": 99.5,
            "ask": 100.5,
            "quote_age_sec": 0.5,
            "quote_source": "option_chain_live",
            "option_ltp_source": "option_chain_live",
        },
        market_data={
            "symbol": "NIFTY",
            "option_chain": [],
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True, "mode": "LIVE"},
        },
        market_ctx=type("Ctx", (), {"mode": "LIVE", "allow_stale_quotes": False, "is_market_open": True})(),
        direction="BUY_CALL",
    )

    assert ok is False
    assert payload["reason_code"] == "contract_resolution_fallback_blocked"
    assert payload["contract_resolution_fallback_used"] is True
