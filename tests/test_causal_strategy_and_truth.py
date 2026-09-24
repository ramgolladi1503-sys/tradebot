"""Offline contracts for Hops 5–12 under canonical CAS shadow-only authority.

Fixtures are synthetic unit inputs, never replay/live proof.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from core.cas_primitive_producer import CASPrimitiveStore
from core.causal_pulse import create_native_pulse
from core.causal_strategy_harness import evaluate_causal_strategies
from core.causal_shadow_decision import evaluate_shadow_decision
from core.causal_trade_truth_emitter import build_canonical_trade_truth

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "b" * 40


def _epoch(h, m, offset=0.0):
    return datetime(2026, 9, 23, h, m, tzinfo=IST).timestamp() + offset


def _authoritative_fixture(tmp_path, session):
    store = CASPrimitiveStore(
        tmp_path / "cas.json", session_id=session,
        source_sha=SOURCE, underlying_token=256265,
    )
    for name, h, m, price in (
        ("0915", 9, 15, 100.0), ("1000", 10, 0, 101.0),
        ("1514", 15, 14, 25000.0),
    ):
        at = _epoch(h, m)
        store.capture(
            name, at, {
                "underlying_symbol": "NIFTY", "last_price": price,
                "timestamp_epoch": at + 0.1,
                "source_timestamp_epoch": at + 0.1,
                "receive_timestamp_epoch": at + 0.3,
                "timestamp_authority": "EXCHANGE_TIMESTAMP",
                "timestamp_fallback_used": False,
            },
            capture_timestamp_ist=datetime.fromtimestamp(at + 0.3, timezone.utc).astimezone(IST).isoformat(),
        )
    return store


def _eval(tmp_path, symbols=None, session="cas-test"):
    pulse = create_native_pulse(
        session_id=session, sequence_num=1, producer_sha=SOURCE,
        timestamp_epoch=_epoch(15, 14, 0.8), payload={"unit": True},
    )
    symbols = symbols if symbols is not None else [
        {"symbol": "NIFTY", "instrument_token": 256265, "feed_ok": True},
    ]
    result = evaluate_causal_strategies(
        pulse=pulse, market_snapshot={"market_open": True, "nifty_ltp": 25000.0},
        feed_health_truth={"symbols": symbols},
        cas_primitive_store=_authoritative_fixture(tmp_path, session),
    )
    return pulse, result


def test_causal_12hop_shadow_lineage(tmp_path):
    pulse, result = _eval(tmp_path)
    assert result.evaluated_symbol_count == 1
    assert len(result.candidates) == 1
    assert result.candidates[0].strategy_id == "CAS_MORNING_REVERSAL_SHORT_HORIZON_V1"
    assert result.candidates[0].execution_eligible is False
    decisions = evaluate_shadow_decision(
        pulse=pulse, strategy_result=result, feed_health_truth={},
    )
    assert decisions.selected_candidates == []
    assert decisions.risk_verdict == "NOT_EVALUATED_SHADOW_ONLY"
    assert decisions.orders_placed == 0 and decisions.broker_write_authority is False
    truth = build_canonical_trade_truth(
        pulse=pulse, strategy_result=result, decision_result=decisions,
        market_snapshot={"market_open": True, "nifty_ltp": 25000.0},
        feed_health_truth={},
    )
    assert truth.identity.session_id == pulse.session_id
    assert truth.identity.strategy_id == result.candidates[0].strategy_id
    assert truth.decision.candidate_generated is True
    assert truth.decision.candidate_score is None
    assert truth.decision.rank is None
    assert truth.execution.intended_action == "NO_TRADE"
    assert truth.timing.exchange_timestamp_epoch is None  # pulse is not exchange tick


def test_real_cas_evaluator_called_not_tradebuilder_or_unverified_risk(tmp_path, monkeypatch):
    import core.causal_cas_qualification as adapter
    from strategies.trade_builder import TradeBuilder
    from core.risk_engine import RiskEngine
    called = {"cas": 0, "tradebuilder": 0, "risk": 0}
    original = adapter.evaluate_cas

    def spy(*args, **kwargs):
        called["cas"] += 1
        return original(*args, **kwargs)

    def prohibit_build(*args, **kwargs):
        called["tradebuilder"] += 1
        raise AssertionError("CAS advisory has no verified option quote")

    def prohibit_risk(*args, **kwargs):
        called["risk"] += 1
        raise AssertionError("CAS must not receive fictional portfolio risk PASS")

    monkeypatch.setattr(adapter, "evaluate_cas", spy)
    monkeypatch.setattr(TradeBuilder, "build", prohibit_build)
    monkeypatch.setattr(RiskEngine, "evaluate_trade", prohibit_risk)
    pulse, result = _eval(tmp_path)
    decision = evaluate_shadow_decision(
        pulse=pulse, strategy_result=result, feed_health_truth={},
    )
    assert called == {"cas": 1, "tradebuilder": 0, "risk": 0}
    assert decision.risk_verdict == "NOT_EVALUATED_SHADOW_ONLY"


def test_missing_strategy_inputs_remain_missing_without_manufacturing():
    pulse = create_native_pulse(
        session_id="missing", sequence_num=1, producer_sha=SOURCE,
        payload={"fixture": True},
    )
    result = evaluate_causal_strategies(
        pulse=pulse, market_snapshot={}, feed_health_truth={"symbols": []},
    )
    assert result.evaluated_symbol_count == 0
    assert not result.candidates


def test_unrelated_stock_feed_failure_does_not_veto_nifty_strategy(tmp_path):
    pulse, result = _eval(tmp_path, symbols=[
        {"symbol": "NIFTY", "instrument_token": 256265, "feed_ok": True},
        {"symbol": "TCS", "instrument_token": 895745, "feed_ok": False},
    ])
    assert len(result.candidates) == 1
    assert result.candidates[0].symbol == "NIFTY"
    tcs = next(o for o in result.observations if o.symbol == "TCS")
    assert tcs.applicability_state == "INAPPLICABLE"


def test_stale_quote_keeps_verified_signal_but_blocks_advisory(tmp_path):
    pulse, result = _eval(tmp_path, symbols=[
        {"symbol": "NIFTY", "instrument_token": 256265, "feed_ok": False},
    ])
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.strategy_qualified is True
    assert candidate.advisory_ready is False
    assert candidate.execution_eligible is False
    assert result.executable_candidates == []
    assert result.advisory_candidates == []
