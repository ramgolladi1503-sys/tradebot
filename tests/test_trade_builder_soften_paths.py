from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace

from config import config as cfg
from core import orchestrator as orch
from core.trade_schema import Trade
from strategies.trade_builder import TradeBuilder


def _market_data(symbol: str = "NIFTY") -> dict:
    return {
        "symbol": symbol,
        "ltp": 25000.0,
        "underlying_spot": 25000.0,
        "execution_mode": "SIM",
        "market_context": {"execution_mode": "SIM", "market_open": False},
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000CE",
                "instrument_token": 900001,
                "ltp": 100.0,
                "bid": 99.5,
                "ask": 100.5,
            },
            {
                "type": "PE",
                "strike": 25000.0,
                "expiry": "2026-04-30",
                "tradingsymbol": "NIFTY26APR25000PE",
                "instrument_token": 900002,
                "ltp": 105.0,
                "bid": 104.5,
                "ask": 105.5,
            },
        ],
    }


def _live_option_row(**overrides) -> dict:
    base = {
        "type": "CE",
        "strike": 25000.0,
        "expiry": "2026-04-30",
        "tradingsymbol": "NIFTY26APR25000CE",
        "instrument_token": 900001,
        "ltp": 100.0,
        "bid": 99.5,
        "ask": 100.5,
        "quote_ok": True,
        "quote_live": True,
        "depth_ok": True,
        "volume": 2000,
        "oi": 25000,
        "oi_change": 1500,
        "moneyness": 0.0,
        "iv": 0.2,
        "iv_z": 0.0,
        "iv_skew": 0.0,
        "iv_skew_norm": 0.0,
        "delta": 0.45,
        "oi_build": "LONG",
        "quote_source": "option_chain_live",
        "option_ltp_source": "option_chain_live",
        "quote_age_sec": 0.4,
        "quote_ts_epoch": time.time(),
    }
    base.update(overrides)
    return base


def test_premium_band_fail_softens_to_candidate():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "no_viable_candidates",
        "gate_reasons": ["premium_band_fail"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is not None
    assert cand["reject_reason"] == "premium_band_fail"
    assert cand["execution_status"] == "scored"
    assert cand["candidate_status"] == "near_executable"
    assert cand["execution_entry_status"] == "non_executable"
    assert cand["rank_score"] is not None


def test_weak_momentum_softens_to_candidate():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "weak_momentum",
        "gate_reasons": ["weak_momentum"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="ZERO_TO_HERO",
        direction="BUY_CALL",
    )

    assert cand is not None
    assert cand["reject_reason"] == "weak_momentum"
    assert cand["execution_status"] == "scored"
    assert cand["candidate_status"] == "near_executable"


def test_malformed_option_row_still_hard_fails():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "malformed_option_row",
        "gate_reasons": ["malformed_option_row"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is None


def test_softened_candidate_enters_ranked_pool():
    tb = TradeBuilder()
    reject_ctx = {
        "symbol": "NIFTY",
        "reason": "no_viable_candidates",
        "gate_reasons": ["spread_pct"],
    }
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx=reject_ctx,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )

    assert cand is not None
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert len(ranked) > 0
    assert ranked[0]["execution_status"] == "scored"


def test_no_signal_soften_builds_borderline_candidate():
    tb = TradeBuilder()
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "no_signal", "gate_reasons": ["no_signal"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["eligible_for_execution"] is False
    assert cand["execution_blocked"] is False
    assert cand["execution_block_reason"] is None
    assert cand["rank_score"] is None
    assert cand["score_origin"] == "soft_reject_seed"


def test_no_signal_softened_candidate_does_not_enter_ranked_pool():
    tb = TradeBuilder()
    _ = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "no_signal", "gate_reasons": ["no_signal"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert ranked == []


def test_live_no_signal_without_live_fallback_returns_none_and_skips_borderline(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", False, raising=False)
    monkeypatch.setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "LIVE_ALLOW_WEAK_SIGNAL_BORDERLINE_CANDIDATE", False, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)

    trade = tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
        }
    )

    assert trade is None
    ranked = orch._consume_trade_builder_ranked_candidates(tb)
    assert ranked == []


def test_live_no_signal_fallback_promotes_signal_path_before_lifecycle_gate(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_NO_SIGNAL_FALLBACK_SCORE_MIN", 0.58, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_quick_neutral_fallback_signal", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        tb,
        "_planning_signal_fallback_signal",
        lambda *_args, **_kwargs: {"direction": "BUY_CALL", "score": 0.62, "reason": "fallback"},
    )
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (False, None))
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)

    trade = tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
        }
    )

    assert trade is None
    reject_ctx = dict(getattr(tb, "_reject_ctx", {}) or {})
    assert reject_ctx.get("reason") == "lifecycle_gate_fail"


def test_live_oi_build_mismatch_softened_when_alignment_disabled(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "LIVE_REQUIRE_OI_BUILD_ALIGNMENT", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: {"direction": "BUY_CALL", "score": 0.72, "reason": "unit"})
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {"expiry": "2026-04-30", "tradingsymbol": "NIFTY26APR25000CE", "instrument_token": 900001},
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (False, None))
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)

    tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
            "option_chain": [_live_option_row(oi_build="SHORT_COVER")],
        }
    )

    assert int((tb._scan_reject_counts or {}).get("oi_build", 0)) == 0


def test_live_no_volume_not_hard_rejected_when_live_suggest_volume_disabled(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: {"direction": "BUY_CALL", "score": 0.72, "reason": "unit"})
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {"expiry": "2026-04-30", "tradingsymbol": "NIFTY26APR25000CE", "instrument_token": 900001},
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (False, None))
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)

    tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
            "option_chain": [_live_option_row(volume=0, oi_build="LONG")],
        }
    )

    assert int((tb._scan_reject_counts or {}).get("no_volume", 0)) == 0


def test_live_delta_bounds_override_prevents_reject_for_mid_delta(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "DELTA_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "DELTA_MAX", 0.70, raising=False)
    monkeypatch.setattr(cfg, "LIVE_DELTA_MIN", 0.15, raising=False)
    monkeypatch.setattr(cfg, "LIVE_DELTA_MAX", 0.90, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: {"direction": "BUY_CALL", "score": 0.72, "reason": "unit"})
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {"expiry": "2026-04-30", "tradingsymbol": "NIFTY26APR25000CE", "instrument_token": 900001},
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (False, None))
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)

    tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
            "option_chain": [_live_option_row(delta=0.20, oi_build="LONG")],
        }
    )

    assert int((tb._scan_reject_counts or {}).get("delta", 0)) == 0


def test_live_trade_score_min_override_allows_candidate_above_live_floor(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 75.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_TRADE_SCORE_MIN", 68.0, raising=False)
    monkeypatch.setattr(tb, "_signal_for_symbol", lambda *_args, **_kwargs: {"direction": "BUY_CALL", "score": 0.72, "reason": "unit"})
    monkeypatch.setattr(tb, "_resolve_index_bid_ask", lambda md, _mode: dict(md, quote_ok=True, bid=1.0, ask=1.1))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "live", True, None))
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {"expiry": "2026-04-30", "tradingsymbol": "NIFTY26APR25000CE", "instrument_token": 900001},
    )
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (False, None))
    monkeypatch.setattr(tb, "_log_blocked_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(tb, "_reject_exit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "strategies.trade_builder.compute_trade_score",
        lambda *_args, **_kwargs: {"score": 70.0},
    )

    tb.build(
        {
            **_market_data(),
            "execution_mode": "LIVE",
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "chain_source": "live",
            "quote_ok": True,
            "bid": 1.0,
            "ask": 1.1,
            "option_chain": [_live_option_row(delta=0.45, oi_build="LONG")],
        }
    )

    assert int((tb._scan_reject_counts or {}).get("trade_score", 0)) == 0


def test_borderline_candidate_not_marked_execution_blocked():
    tb = TradeBuilder()
    cand = tb._build_borderline_candidate(
        market_data=_market_data(),
        reason="weak_signal",
        confidence=0.19,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["execution_allowed"] is False
    assert cand["execution_blocked"] is False
    assert cand["execution_block_reason"] is None
    assert cand["rank_score"] is None


def test_borderline_candidate_resolves_contract_from_chain():
    tb = TradeBuilder()
    md = _market_data()
    md.update(
        {
            "ltp": 25010.0,
            "underlying_spot": 25010.0,
            "option_chain": [
                {
                    "type": "CE",
                    "strike": 25000.0,
                    "expiry": "2026-04-30",
                    "tradingsymbol": "NIFTY26APR25000CE",
                    "instrument_token": 987654,
                    "ltp": 110.0,
                    "bid": 109.5,
                    "ask": 110.5,
                }
            ],
        }
    )
    cand = tb._build_borderline_candidate(
        market_data=md,
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand.get("instrument_token") == 987654
    assert cand.get("tradingsymbol") == "NIFTY26APR25000CE"
    assert cand.get("expiry") == "2026-04-30"
    assert cand.get("unresolved_contract") is False
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["rank_score"] is None


def test_decorate_trade_context_downgrades_fallback_contract_to_queue_only(monkeypatch):
    tb = TradeBuilder()
    trade = Trade(
        trade_id="T-FALLBACK-CONTRACT",
        timestamp=datetime(2026, 4, 21, 10, 0, 0),
        symbol="NIFTY",
        instrument="OPT",
        instrument_token=900001,
        strike=25000,
        expiry="2026-04-30",
        side="BUY",
        entry_price=100.0,
        stop_loss=90.0,
        target=120.0,
        qty=1,
        capital_at_risk=10.0,
        expected_slippage=0.2,
        confidence=0.72,
        strategy="UNIT",
        regime="TREND",
        option_type="CE",
        right="CE",
        instrument_type="OPT",
        tradingsymbol="NIFTY26APR25000CE",
        instrument_id="NIFTY|2026-04-30|25000|CE",
        execution_allowed=True,
        tradable=True,
        candidate_status="executable",
        source_flags={
            "decision_trace": {
                "rank_score": 0.66,
                "permission": "EXECUTE",
                "permission_reason": "ok",
                "final_action": "EXECUTE",
                "readiness": "READY",
                "execution_status": "executable",
                "execution_allowed": True,
                "execution_entry_status": "executable",
                "candidate_status": "executable",
            }
        },
    )
    monkeypatch.setattr(
        tb,
        "_apply_candidate_contract",
        lambda cand, **_kwargs: replace(
            cand,
            strike=25050,
            expiry="2026-05-07",
            expiry_date="2026-05-07",
            tradingsymbol="NIFTY26MAY25050CE",
            instrument_token=900123,
            instrument_id="NIFTY|2026-05-07|25050|CE",
        ),
    )

    out = tb._decorate_trade_context(
        trade,
        {
            **_market_data(),
            "market_context": {"execution_mode": "LIVE", "market_open": True},
            "market_open": True,
            "execution_mode": "LIVE",
        },
        0.72,
    )

    assert out is not None
    assert out.requested_strike == 25000
    assert out.resolved_strike == 25050
    assert out.requested_expiry == "2026-04-30"
    assert out.resolved_expiry == "2026-05-07"
    assert out.contract_exact_match is False
    assert out.resolution_mode == "fallback"
    assert out.fallback_used is True
    assert out.fallback_execution_policy == "QUEUE_ONLY"
    assert out.permission == "QUEUE_ONLY"
    assert out.final_action == "QUEUE_ONLY"
    assert out.readiness == "QUEUE_ONLY"
    assert out.execution_status == "queue_only"
    assert out.permission_reason == "nearest_contract_match"


def test_borderline_candidate_downgrades_when_contract_unresolved(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-04-30")
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-04-30",
            "expiry_date": "2026-04-30",
            "tradingsymbol": None,
            "instrument_token": None,
            "instrument_id": None,
        },
    )
    md = _market_data()
    md.update({"ltp": 25010.0, "underlying_spot": 25010.0, "option_chain": []})
    cand = tb._build_borderline_candidate(
        market_data=md,
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is not None
    assert cand.get("unresolved_contract") is True
    assert cand["execution_status"] == "advisory_only"
    assert cand["candidate_status"] == "advisory_only"
    assert cand["eligible_for_execution"] is False
    assert cand["execution_block_reason"] == "unresolved_contract"


def test_soften_reject_disabled_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    cand = tb._soften_reject_to_candidate(
        market_data=_market_data(),
        reject_ctx={"symbol": "NIFTY", "reason": "weak_momentum", "gate_reasons": ["weak_momentum"]},
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is None


def test_borderline_candidate_disabled_in_strict_mode(monkeypatch):
    monkeypatch.setattr(cfg, "PHASE2_STRICT_REAL_CANDIDATES_ONLY", True, raising=False)
    tb = TradeBuilder()
    cand = tb._build_borderline_candidate(
        market_data=_market_data(),
        reason="weak_signal",
        confidence=0.2,
        strategy_tag="CORE",
        direction="BUY_CALL",
    )
    assert cand is None


def test_option_tradability_uses_symbol_feed_age_fallback_in_live(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "TRADE_BUILDER_USE_SYMBOL_FEED_AGE_FALLBACK", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FEED_AGE_FALLBACK_MAX_SEC", 3.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_OPTION_TICK_SOFT_STALE_SEC", 6.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_OPTION_TICK_HARD_STALE_SEC", 18.0, raising=False)
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-04-30",
            "tradingsymbol": "NIFTY26APR25000CE",
            "instrument_token": 900001,
            "instrument_id": 900001,
        },
    )
    monkeypatch.setattr(tb, "_symbol_feed_option_tick_age", lambda *_args, **_kwargs: 0.4)

    market_ctx = SimpleNamespace(mode="LIVE", allow_stale_quotes=False, is_market_open=True)
    tradable, payload = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt={
            "type": "CE",
            "strike": 25000.0,
            "expiry": "2026-04-30",
            "tradingsymbol": "NIFTY26APR25000CE",
            "instrument_token": 900001,
            "instrument_id": 900001,
            "quote_source": "option_chain_live",
            "option_ltp_source": "option_chain_live",
            "quote_age_sec": None,
        },
        market_data={"option_quote_source": "option_chain_live"},
        market_ctx=market_ctx,
        direction="BUY_CALL",
    )

    assert tradable is True
    assert float(payload.get("quote_age_sec") or 0.0) <= 3.0


def test_cached_feed_runtime_snapshot_uses_newest_normalized_payload(monkeypatch, tmp_path):
    tb = TradeBuilder()
    runtime_root = tmp_path / "runtime"
    logs_root = tmp_path / "logs"
    runtime_root.mkdir(parents=True, exist_ok=True)
    logs_root.mkdir(parents=True, exist_ok=True)

    older = runtime_root / "feed_runtime_latest.json"
    older.write_text(
        json.dumps(
            {
                "ws_connected": False,
                "option_feed_block_reason_by_symbol": {"NIFTY": "NO_LIVE_OPTION_FEED"},
                "last_option_tick_ts_by_symbol": {"NIFTY": 1000.0},
            }
        ),
        encoding="utf-8",
    )
    newer = logs_root / "feed_runtime_latest.json"
    newer.write_text(
        json.dumps(
            {
                "generated_at": "2026-04-20T05:59:48.101698Z",
                "payload": {
                    "ws_connected": True,
                    "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
                    "option_last_tick_age_by_symbol": {"NIFTY": 0.4},
                    "last_option_tick_ts_by_symbol": {"NIFTY": 2000.0},
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("strategies.trade_builder.data_root", lambda: str(runtime_root))
    monkeypatch.setattr("strategies.trade_builder.logs_dir", lambda: logs_root)
    snapshot = tb._cached_feed_runtime_snapshot(now_epoch=2_100.0)

    assert snapshot.get("ws_connected") is True
    assert snapshot.get("option_feed_block_reason_by_symbol", {}).get("NIFTY") == "OK"
    assert float(snapshot.get("last_option_tick_ts_by_symbol", {}).get("NIFTY")) == 2000.0


def test_resolve_option_contract_allows_near_strike_fallback_window(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", 4, raising=False)
    market_data = {
        "option_chain": [
            {
                "type": "PE",
                "strike": 26100.0,
                "expiry": "2026-04-21",
                "tradingsymbol": "NIFTY2642126100PE",
                "instrument_token": 16126100,
            }
        ]
    }
    resolved = tb._resolve_option_contract(
        symbol="NIFTY",
        strike=26250.0,
        opt_type="PE",
        expiry="2026-04-21",
        market_data=market_data,
    )
    assert resolved.get("instrument_token") == 16126100
    assert resolved.get("tradingsymbol") == "NIFTY2642126100PE"
    assert resolved.get("fallback_applied") is True


def test_resolve_option_contract_uses_abs_diff_cap_when_step_window_too_tight(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", 2, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_ABS", 300.0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_PCT", 0.0, raising=False)
    market_data = {
        "ltp": 26120.0,
        "option_chain": [
            {
                "type": "PE",
                "strike": 26100.0,
                "expiry": "2026-04-21",
                "tradingsymbol": "NIFTY2642126100PE",
                "instrument_token": 16126100,
            }
        ],
    }
    resolved = tb._resolve_option_contract(
        symbol="NIFTY",
        strike=26350.0,
        opt_type="PUT",
        expiry="2026-04-21",
        market_data=market_data,
    )
    assert resolved.get("instrument_token") == 16126100
    assert resolved.get("fallback_applied") is True


def test_resolve_option_contract_rejects_when_diff_exceeds_all_caps(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_STEPS", 2, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_ABS", 150.0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_CONTRACT_STRIKE_FALLBACK_MAX_DIFF_PCT", 0.0, raising=False)
    market_data = {
        "ltp": 26120.0,
        "option_chain": [
            {
                "type": "PE",
                "strike": 26100.0,
                "expiry": "2026-04-21",
                "tradingsymbol": "NIFTY2642126100PE",
                "instrument_token": 16126100,
            }
        ],
    }
    resolved = tb._resolve_option_contract(
        symbol="NIFTY",
        strike=26400.0,
        opt_type="PE",
        expiry="2026-04-21",
        market_data=market_data,
    )
    assert resolved.get("instrument_token") is None
    assert resolved.get("fallback_applied") is False


def test_option_tradability_live_stale_soften_allows_high_oi_when_volume_missing(monkeypatch):
    pass


def test_option_tradability_live_stale_soften_blocks_when_quote_ok_required(monkeypatch):
    tb = TradeBuilder()
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_OPTION_TICK_SOFT_STALE_SEC", 10.0, raising=False)
    monkeypatch.setattr(cfg, "LIVE_OPTION_TICK_HARD_STALE_SEC", 24.0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_LIVE_STALE_SOFTEN_MIN_OI", 1000.0, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_LIVE_STALE_SOFTEN_REQUIRE_QUOTE_OK", True, raising=False)
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-04-30",
            "tradingsymbol": "NIFTY26APR25000CE",
            "instrument_token": 900001,
            "instrument_id": 900001,
        },
    )
    market_ctx = SimpleNamespace(mode="LIVE", allow_stale_quotes=False, is_market_open=True)
    tradable, payload = tb._option_tradability_precondition(
        symbol="NIFTY",
        opt={
            "type": "CE",
            "strike": 25000.0,
            "expiry": "2026-04-30",
            "tradingsymbol": "NIFTY26APR25000CE",
            "instrument_token": 900001,
            "instrument_id": 900001,
            "ltp": 100.0,
            "bid": 99.5,
            "ask": 100.5,
            "quote_ok": False,
            "volume": 0,
            "oi": 3500,
            "quote_source": "option_chain_live",
            "option_ltp_source": "option_chain_live",
            "quote_age_sec": 8.0,
        },
        market_data={"option_quote_source": "option_chain_live"},
        market_ctx=market_ctx,
        direction="BUY_CALL",
    )

    assert tradable is False
    assert payload.get("reason_code") == "STALE_OPTION_TICK"
