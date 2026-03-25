from __future__ import annotations

from dataclasses import asdict
import logging
import json

from config import config as cfg
from core import review_queue
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


class _PredictorFixed:
    model_version = "stub"
    shadow_version = None

    def __init__(self, value: float):
        self.value = float(value)

    def predict_confidence(self, _feats):
        return self.value


class _PredictorNone:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return None


class _MicroPredictorFixed:
    def __init__(self, value: float):
        self.value = float(value)

    def predict_confidence(self, _features):
        return self.value


def _patch_builder(monkeypatch, builder):
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda _md, force_family=None: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None), raising=True)
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(trade_builder_module, "compute_trade_score", lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0})
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)


def _base_market_data(option_ltp: float) -> dict:
    return {
        "symbol": "NIFTY",
        "market_open": True,
        "valid": True,
        "ltp": 25000.0,
        "vwap": 24990.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live",
        "quote_ok": True,
        "bid": 24999.0,
        "ask": 25001.0,
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "option_chain": [
            {
                "type": "CE",
                "strike": 25000,
                "expiry": "2026-02-26",
                "tradingsymbol": "NIFTY26FEB25000CE",
                "instrument_token": 123456,
                "ltp": option_ltp,
                "bid": option_ltp - 1.0,
                "ask": option_ltp + 1.0,
                "quote_ok": True,
                "quote_live": True,
                "quote_age_sec": 1.0,
                "quote_ts_epoch": 1771400000.0,
                "depth_ok": True,
                "volume": 5000,
                "oi": 20000,
                "oi_change": 1000,
                "iv": 0.2,
                "iv_z": 0.0,
                "iv_skew": 0.0,
                "delta": 0.3,
                "moneyness": 0.0,
            }
        ],
    }


_STAGED_CONFIDENCE_FIELDS = (
    "confidence_model_raw",
    "confidence_model_component",
    "confidence_micro_component",
    "confidence_micro_blend_method",
    "confidence_after_micro",
    "confidence_after_alpha",
    "confidence_after_latency",
    "confidence_before_soft_veto",
    "confidence_after_soft_veto",
    "confidence_penalty_soft_veto_total",
    "confidence_penalty_soft_veto_reasons",
    "confidence_gate_threshold",
    "confidence_raw_gate_threshold",
    "confidence_final_gate_threshold",
    "confidence_rejection_stage",
    "confidence_base",
    "confidence_penalty_total",
    "confidence_penalty_reasons",
)


def _serialize_trade_row(tmp_path, monkeypatch, trade):
    qpath = tmp_path / "review_queue.json"
    monkeypatch.setattr(review_queue, "QUEUE_PATH", qpath)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    monkeypatch.setattr(cfg, "MANUAL_APPROVAL", False, raising=False)
    monkeypatch.setattr(cfg, "ENABLE_EQUITIES", True, raising=False)
    monkeypatch.setattr(review_queue, "ensure_subscribed_tokens", lambda *args, **kwargs: True)
    monkeypatch.setattr(review_queue, "get_ltp", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(review_queue, "is_market_open_ist", lambda: True)
    review_queue.add_to_queue(asdict(trade))
    return json.loads(qpath.read_text())[-1]


def _assert_staged_confidence_fields_present(row: dict):
    for key in _STAGED_CONFIDENCE_FIELDS:
        assert key in row


def build_id(symbol: str, expiry: str, strike: int, opt_type: str) -> str:
    return f"{symbol}|OPT|{expiry}|{strike}|{opt_type}"


def test_premium_band_summary_logging_and_spam_suppressed(monkeypatch, caplog):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (10.0, 20.0)}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    opt2 = dict(market_data["option_chain"][0])
    opt2["strike"] = 25050
    opt2["tradingsymbol"] = "NIFTY26FEB25050CE"
    opt2["instrument_token"] = 123457
    market_data["option_chain"].append(opt2)

    calls: list[str] = []
    orig = builder._log_blocked_candidate

    def _spy(*args, **kwargs):
        if len(args) > 2:
            calls.append(str(args[2]))
        elif "reason_code" in kwargs:
            calls.append(str(kwargs["reason_code"]))
        return orig(*args, **kwargs)

    monkeypatch.setattr(builder, "_log_blocked_candidate", _spy, raising=True)

    caplog.set_level(logging.INFO)
    builder.build(market_data, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert caplog.text.count("PREMIUM_BAND_FAIL_SUMMARY") == 1
    assert "premium_band_fail_count=2" in caplog.text
    assert "premium_band_fail" not in calls


def test_premium_band_out_of_band_does_not_kill_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (10.0, 20.0)}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.9))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    assert "premium_band_fail" in (trade.source_flags.get("gates_failed") or [])


def test_fallback_top_ranked_candidate_when_selection_none(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _select_best_stub(_candidates, **_kwargs):
        return None, [
            {
                "trade_id": "cand_1",
                "rank_score": 0.91,
                "confidence": 0.42,
                "size_mult": 1.0,
                "tradable_reasons_blocking": [],
                "source_flags": {},
            }
        ]

    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _select_best_stub, raising=True)
    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=True, allow_baseline=False)

    assert trade is not None
    if isinstance(trade, dict):
        assert trade.get("fallback_candidate") is True
        assert trade.get("fallback_reason") == "no_viable_candidates_top_ranked"
        assert trade.get("execution_allowed") is False
    else:
        assert trade.source_flags.get("fallback_candidate") is True
        assert trade.reason == "no_viable_candidates_top_ranked"
        assert trade.execution_allowed is False


def test_build_sets_concrete_reject_reason_when_no_trade_and_no_fallback(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "STRICT_STRATEGY_SCORE", 0.1, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    def _select_best_stub(_candidates, **_kwargs):
        return None, []

    monkeypatch.setattr(trade_builder_module, "select_best_opportunity", _select_best_stub, raising=True)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert str(builder._reject_ctx.get("reason") or "").strip() in {"no_viable_candidates", "no_candidates_survived"}


def test_invalid_snapshot_still_blocks_trade(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    builder = TradeBuilder()

    trade = builder.build(
        {"symbol": "NIFTY", "valid": False, "invalid_reason": "invalid_snapshot"},
        quick_mode=False,
    )

    assert trade is None
    assert builder._reject_ctx.get("reason") == "invalid_snapshot"


def _make_quick_synth_trade(builder: TradeBuilder, market_data: dict):
    symbol = str(market_data["symbol"])
    opt_type = "CE"
    underlying_spot = 25000.0
    spot_source = "ltp"
    ts = "UNIT"
    expiry_resolved = "2026-02-26"
    step = (getattr(cfg, "STRIKE_STEP_BY_SYMBOL", {}) or {}).get(symbol, getattr(cfg, "STRIKE_STEP", 50))
    atm_strike = int(round(float(underlying_spot) / step) * step) if step else 0
    contract = builder._resolve_option_contract(symbol, atm_strike, opt_type, expiry_resolved, market_data)
    expiry_resolved = contract.get("expiry") or expiry_resolved
    tradingsymbol = contract.get("tradingsymbol")
    instrument_token = contract.get("instrument_token")
    instrument_id = contract.get("instrument_id")
    instrument_type, _, qty_units, ident_err = builder._identity_fields(symbol, "OPT", expiry_resolved, atm_strike, opt_type, 1)
    assert ident_err is None
    assert tradingsymbol
    assert instrument_id
    min_p, max_p = (getattr(cfg, "PREMIUM_BANDS", {}) or {}).get(
        symbol,
        (getattr(cfg, "MIN_PREMIUM", 40), getattr(cfg, "MAX_PREMIUM", 150)),
    )
    ltp_opt = max(min_p, min(max_p, float(underlying_spot) * 0.004))
    bid = round(ltp_opt * 0.995, 2)
    ask = round(ltp_opt * 1.005, 2)
    mark_price = round((bid + ask) / 2.0, 2)
    synthetic_opt = {
        "bid": bid,
        "ask": ask,
        "ltp": mark_price,
        "last_price": mark_price,
        "quote_ok": True,
        "quote_live": True,
        "volume": 1000,
        "spread_pct": ((ask - bid) / mark_price) if mark_price else None,
    }
    entry_price = ask
    entry_price, entry_condition, entry_ref_price = builder._apply_entry_trigger(entry_price, side="BUY", quick_mode=True)
    option_risk = builder._option_risk_proxy(entry_price, bid, ask)
    stop_loss, target = builder._opt_risk_levels(entry_price, bid, ask, option_risk, stop_mult=1.0, target_mult=1.5)
    intent = builder.trade_intent_flags(market_data, opt={"quote_ok": True}, additional_blockers=[])
    quick_final_gate_threshold = builder._final_confidence_gate_threshold("NEUTRAL", quick_mode=True)
    quick_raw_gate_threshold = builder._raw_confidence_gate_threshold("NEUTRAL", quick_mode=True)
    synthetic_confidence = float(max(0.5, quick_final_gate_threshold))
    return trade_builder_module.Trade(
        trade_id=f"{symbol}-{opt_type}-ATM-QK-{ts}",
        timestamp=trade_builder_module.datetime.now(),
        symbol=symbol,
        instrument="OPT",
        instrument_type=instrument_type,
        right=opt_type,
        instrument_id=instrument_id,
        instrument_token=instrument_token,
        strike=atm_strike,
        expiry=expiry_resolved,
        expiry_date=expiry_resolved,
        tradingsymbol=tradingsymbol,
        option_type=opt_type,
        side="BUY",
        entry_price=round(entry_price, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        qty=1,
        qty_lots=1,
        qty_units=qty_units,
        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
        capital_at_risk=round(max(entry_price - stop_loss, 0.01), 2),
        expected_slippage=0.0,
        confidence=round(synthetic_confidence, 3),
        strategy="QUICK_SYNTH",
        regime=market_data.get("regime", "NEUTRAL"),
        tier="EXPLORATION",
        day_type=market_data.get("day_type", "UNKNOWN"),
        signal_price=None,
        entry_price_source="ask",
        expected_entry=round(entry_price, 2),
        expected_entry_source="ask",
        **builder._option_liquidity_fields(synthetic_opt),
        entry_condition=entry_condition,
        entry_ref_price=entry_ref_price,
        alpha_confidence=None,
        alpha_uncertainty=None,
        size_mult=1.0,
        tradable=bool(intent["tradable"]),
        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
        planning_only=bool(intent["planning_only"]),
        execution_allowed=bool(intent["execution_allowed"]),
        reason=intent["execution_reason"],
        source_flags=dict(intent["source_flags"]),
        underlying_spot=underlying_spot,
        spot_source=spot_source,
        option_ltp_source=None,
        chain_source=market_data.get("chain_source") or "synthetic",
        **builder._staged_confidence_payload(
            confidence=synthetic_confidence,
            model_raw=synthetic_confidence,
            model_component=synthetic_confidence,
            micro_blend_method="model_only",
            before_soft_veto=synthetic_confidence,
            after_soft_veto=synthetic_confidence,
            penalty_soft_veto_total=0.0,
            penalty_soft_veto_reasons=[],
            gate_threshold=quick_final_gate_threshold,
            raw_gate_threshold=quick_raw_gate_threshold,
            final_gate_threshold=quick_final_gate_threshold,
            base=synthetic_confidence,
            penalty_total=0.0,
            penalty_reasons=[],
        ),
    )


def _make_equity_fallback_trade(builder: TradeBuilder, market_data: dict):
    symbol = str(market_data["symbol"])
    ltp = float(market_data["ltp"])
    vwap = float(market_data.get("vwap") or ltp)
    direction = "BUY_CALL"
    atr = market_data.get("atr", max(1.0, ltp * 0.002))
    vwap_dist = (ltp - vwap) / vwap if vwap else 0.0
    base_conf = min(0.8, max(0.5, 0.5 + abs(vwap_dist) * 10))
    strat_name = "EQ_TREND"
    side = "BUY" if direction == "BUY_CALL" else "SELL"
    stop_loss = ltp - atr if side == "BUY" else ltp + atr
    target = ltp + atr * 1.5 if side == "BUY" else ltp - atr * 1.5
    instrument_type, instrument_id, qty_units, ident_err = builder._identity_fields(
        symbol,
        "EQ",
        getattr(cfg, "FUT_EXPIRY", ""),
        None,
        None,
        1,
    )
    assert ident_err is None
    intent = builder.trade_intent_flags(
        market_data,
        opt={"quote_ok": bool(market_data.get("quote_ok", True)), "quote_age_sec": market_data.get("quote_age_sec")},
    )
    final_gate_threshold = builder._final_confidence_gate_threshold(market_data.get("regime"), quick_mode=False)
    return trade_builder_module.Trade(
        trade_id=f"{symbol}-FUT-UNIT",
        timestamp=trade_builder_module.datetime.now(),
        symbol=symbol,
        instrument="EQ",
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        instrument_token=None,
        strike=0,
        expiry=str(getattr(cfg, "FUT_EXPIRY", "")),
        side=side,
        entry_price=round(ltp, 2),
        stop_loss=round(stop_loss, 2),
        target=round(target, 2),
        qty=1,
        qty_lots=1,
        qty_units=qty_units,
        validity_sec=int(getattr(cfg, "TELEGRAM_TRADE_VALIDITY_SEC", 180)),
        capital_at_risk=round(abs(ltp - stop_loss), 2),
        expected_slippage=0.0,
        confidence=round(base_conf, 3),
        strategy=strat_name,
        regime=market_data.get("regime", "NEUTRAL"),
        tier="MAIN",
        day_type=market_data.get("day_type", "UNKNOWN"),
        alpha_confidence=None,
        alpha_uncertainty=None,
        size_mult=1.0,
        tradable=bool(intent["tradable"]),
        tradable_reasons_blocking=list(intent["tradable_reasons_blocking"]),
        planning_only=bool(intent["planning_only"]),
        execution_allowed=bool(intent["execution_allowed"]),
        reason=intent["execution_reason"],
        source_flags=dict(intent["source_flags"]),
        **builder._staged_confidence_payload(
            confidence=base_conf,
            model_raw=base_conf,
            model_component=base_conf,
            micro_blend_method="model_only",
            before_soft_veto=base_conf,
            after_soft_veto=base_conf,
            penalty_soft_veto_total=0.0,
            penalty_soft_veto_reasons=[],
            gate_threshold=final_gate_threshold,
            final_gate_threshold=final_gate_threshold,
            base=base_conf,
            penalty_total=0.0,
            penalty_reasons=[],
        ),
    )


def test_paper_orb_pending_is_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_CONFLICT_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_SOFT_VETO_CONF_PENALTY", 0.04, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["orb_bias"] = "PENDING"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert "orb_pending" in (trade.source_flags.get("soft_veto_codes") or [])
    assert float(trade.confidence_before_soft_veto) == 0.95
    assert float(trade.confidence_after_soft_veto) == 0.91
    assert float(trade.confidence_penalty_soft_veto_total) == 0.04
    assert trade.confidence_penalty_soft_veto_reasons == ["orb_pending"]


def test_paper_orb_neutral_is_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "PLANNING_ORB_NEUTRAL_ALLOW", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["orb_bias"] = "NEUTRAL"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert "orb_neutral_blocked" in (trade.source_flags.get("soft_veto_codes") or [])


def test_premium_out_of_band_is_soft_veto_when_liquid(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.06, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.10, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=180.0)

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert trade.source_flags.get("premium_soft_veto") is True
    assert "premium_out_of_band" in (trade.source_flags.get("soft_veto_codes") or [])
    assert "premium_out_of_band" not in (trade.source_flags.get("gates_failed") or [])
    assert "premium_out_of_band" not in (trade.source_flags.get("warning_codes") or [])
    assert float(trade.confidence_before_soft_veto) == 0.95
    assert 0.85 <= float(trade.confidence_after_soft_veto) <= 0.89
    assert 0.06 <= float(trade.confidence_penalty_soft_veto_total) <= 0.10
    assert "premium_out_of_band" in list(trade.confidence_penalty_soft_veto_reasons)


def test_stale_quote_survives_as_advisory_gate_without_soft_penalty(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["market_open"] = False
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert "stale_option_quote" in (trade.source_flags.get("gates_failed") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("warning_codes") or [])
    assert trade.source_flags.get("execution_block_type") == "advisory"
    assert trade.order_policy == "advisory"
    assert trade.order_policy_reason == "data_not_live"


def test_paper_stale_option_tick_survives_as_advisory_gate_without_soft_penalty(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert "stale_option_quote" in (trade.source_flags.get("gates_failed") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "stale_option_quote" not in (trade.source_flags.get("warning_codes") or [])


def test_live_market_open_stale_option_tick_remains_rejected(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("STALE_OPTION_TICK", 0)) >= 1


def test_low_volume_becomes_warning_without_duplicate_suppression(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["option_chain"][0]["volume"] = 25

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert "low_volume" in (trade.source_flags.get("warning_codes") or [])
    assert "low_volume" not in (trade.source_flags.get("soft_veto_codes") or [])
    assert "low_volume" not in (trade.source_flags.get("gates_failed") or [])


def test_live_missing_option_bidask_survives_as_non_executable_candidate(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    md["quote_ok"] = True
    md["bid"] = 24999.0
    md["ask"] = 25001.0
    opt = md["option_chain"][0]
    opt["bid"] = None
    opt["ask"] = None
    opt["quote_source"] = "last"
    opt["option_ltp_source"] = "last"
    opt["last_price"] = 100.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.selected_for_execution is False
    assert "option_bidask_missing" in (trade.source_flags.get("gates_failed") or [])


def test_display_only_last_price_candidate_survives_but_is_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_DISPLAY_ONLY_OPTION_CANDIDATES", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["bid"] = None
    opt["ask"] = None
    opt["best_bid"] = None
    opt["best_ask"] = None
    opt["depth_ok"] = False
    opt["quote_ok"] = True
    opt["quote_live"] = True
    opt["price_source"] = "last"
    opt["quote_source"] = "last"
    opt["option_ltp_source"] = "last"
    opt["last_price"] = 100.0

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.selected_for_execution is False
    assert "option_bidask_missing" in (trade.source_flags.get("gates_failed") or [])
    assert "option_depth_missing" in (trade.source_flags.get("warning_codes") or [])
    assert int(builder._last_scan_summary.get("total_candidates") or 0) >= 1
    assert int(builder._last_scan_summary.get("accepted") or 0) >= 1


def test_dynamic_premium_band_uses_chain_percentiles_not_global_clamp(monkeypatch):
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (40.0, 150.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_PERCENTILE_LOW", 0.10, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_PERCENTILE_HIGH", 0.90, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_ATM_MONEYNESS_MAX", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_MIN_ROWS", 6, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BAND_MIN_VOLUME", 1, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    chain = [
        {"expiry": "2026-02-26", "ltp": 10 + (i * 20), "volume": 100, "moneyness": 0.01}
        for i in range(10)
    ]
    bands = builder._dynamic_premium_bands("NIFTY", chain)
    assert "2026-02-26" in bands
    band_min, band_max = bands["2026-02-26"]
    # Global fallback band is 40..150; dynamic band should not be hard-clamped to it.
    assert band_min < 40.0
    assert band_max > 150.0


def test_paper_missing_quote_depth_is_rejected_by_option_tradability_precondition(monkeypatch):
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_ALLOW_NON_LIVE_STALE_OPTION_TICK_ADVISORY", False, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_DEPTH_QUOTES_FOR_TRADE", True, raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_VOLUME_FOR_TRADE", True, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    md = _base_market_data(option_ltp=100.0)
    opt = md["option_chain"][0]
    opt["quote_ok"] = False
    opt["quote_live"] = False
    opt["quote_ts_epoch"] = None
    opt["quote_age_sec"] = 999.0
    opt["depth_ok"] = False
    opt["volume"] = 0
    opt["bid"] = None
    opt["ask"] = None

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is None
    assert int(builder._scan_reject_counts.get("STALE_OPTION_TICK", 0)) >= 1


def test_trade_builder_candidate_passes_raw_and_final_confidence_gates(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.52))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_model_raw) == 0.52
    assert float(trade.confidence_gate_threshold) == 0.31
    assert float(trade.confidence_raw_gate_threshold) == 0.44
    assert float(trade.confidence_final_gate_threshold) == 0.31


def test_trade_builder_candidate_fails_final_confidence_gate_after_soft_veto(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.33, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.08, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.14, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.46))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=300.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_final_gate", 0)) >= 1


def test_multiple_soft_vetoes_are_bounded_and_interpretable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", True, raising=False)
    monkeypatch.setattr(cfg, "ORB_HARD_BLOCK_LIVE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_NEUTRAL_ALLOW", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_SOFT_VETO_CONF_PENALTY", 0.05, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_BANDS", {"NIFTY": (20.0, 120.0)}, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MIN", 0.07, raising=False)
    monkeypatch.setattr(cfg, "PREMIUM_SOFT_VETO_CONF_PENALTY_MAX", 0.12, raising=False)
    monkeypatch.setattr(cfg, "SOFT_VETO_CONF_PENALTY_MAX_TOTAL", 0.10, raising=False)
    monkeypatch.setattr(cfg, "MIN_VOLUME_FILTER", 500, raising=False)
    monkeypatch.setattr(cfg, "MAX_SPREAD_PCT", 0.02, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.85))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)
    md = _base_market_data(option_ltp=300.0)
    md["orb_bias"] = "PENDING"

    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_before_soft_veto) == 0.85
    assert float(trade.confidence_penalty_soft_veto_total) == 0.10
    assert float(trade.confidence_after_soft_veto) == 0.75
    assert trade.confidence_penalty_soft_veto_reasons == ["orb_pending", "premium_out_of_band"]


def test_trade_builder_candidate_fails_raw_confidence_gate_early(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.50, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.42))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_raw_gate", 0)) >= 1


def test_micro_overlay_keeps_strong_model_from_collapsing(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.40, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.82))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.20), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert float(trade.confidence_model_component) == 0.82
    assert float(trade.confidence_micro_component) == 0.20
    assert trade.confidence_micro_blend_method == "bounded_overlay"
    assert float(trade.confidence_after_micro) == 0.72
    assert float(trade.confidence_after_micro) > 0.50


def test_micro_overlay_does_not_overpromote_weak_model(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.35, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.25, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.22))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.92), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is None
    assert int(builder._scan_reject_counts.get("confidence_raw_gate", 0)) >= 1


def test_micro_confidence_fallback_allows_missing_model(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "USE_MICRO_MODEL", True, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_WEIGHT", 0.25, raising=False)
    monkeypatch.setattr(cfg, "MICRO_CONF_OVERLAY_MAX_DELTA", 0.10, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.45, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.35, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorNone())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_get_micro_predictor", lambda: _MicroPredictorFixed(0.58), raising=True)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    assert trade.confidence_model_component is None
    assert float(trade.confidence_micro_component) == 0.58
    assert trade.confidence_micro_blend_method == "micro_fallback"
    assert float(trade.confidence_after_micro) == 0.58


def test_planning_fallback_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    market_data = _base_market_data(option_ltp=100.0)
    market_data["option_chain"] = []

    trade = builder._build_planning_no_signal_trade(market_data, ltp=25000.0, vwap=24990.0)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "NO_SIGNAL_PLANNING"
    assert row["confidence_model_raw"] == row["builder_confidence"]
    assert row["confidence_after_soft_veto"] == row["builder_confidence"]
    assert row["confidence_final"] == row["gating_final_confidence"]
    assert row["confidence"] == row["confidence_final"]
    assert row["confidence_micro_component"] is None
    assert row["confidence_after_micro"] is None
    assert row["confidence_penalty_soft_veto_total"] == 0.0


def test_quick_synthetic_fallback_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder, "_decorate_trade_context", lambda trade, *_args, **_kwargs: trade, raising=True)
    monkeypatch.setattr(builder, "_resolve_underlying_spot", lambda *_args, **_kwargs: (25000.0, "ltp", True, None), raising=True)
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": expiry or "2026-02-26",
            "tradingsymbol": f"{symbol}{strike}{opt_type}",
            "instrument_token": 123456,
            "instrument_id": build_id(symbol, expiry or "2026-02-26", strike, opt_type),
        },
        raising=True,
    )
    monkeypatch.setattr(builder.execution, "estimate_slippage", lambda *_args, **_kwargs: 0.0, raising=False)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["option_chain"] = []
    market_data["chain_source"] = "live"

    trade = _make_quick_synth_trade(builder, market_data)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "QUICK_SYNTH"
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_micro_blend_method"] == "model_only"
    assert row["confidence_raw_gate_threshold"] == 0.35
    assert abs(float(row["confidence_final_gate_threshold"]) - 0.31) < 0.011


def test_equity_fallback_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "ENABLE_EQUITIES", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.30, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)
    monkeypatch.setattr(builder, "_decorate_trade_context", lambda trade, *_args, **_kwargs: trade, raising=True)

    market_data = _base_market_data(option_ltp=100.0)
    market_data["instrument"] = "EQ"
    market_data["option_chain"] = []

    trade = _make_equity_fallback_trade(builder, market_data)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "EQ_TREND"
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_after_alpha"] is None
    assert row["confidence_final_gate_threshold"] == 0.30
    assert row["confidence_penalty_total"] == 0.0


def test_main_path_trade_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_RAW_CONFIDENCE_MIN", 0.44, raising=False)
    monkeypatch.setattr(cfg, "TRADE_BUILDER_FINAL_CONFIDENCE_MIN", 0.31, raising=False)
    monkeypatch.setattr(cfg, "REGIME_PROBA_MULT", {"TREND": 1.0}, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorFixed(0.52))
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(builder.execution, "latency_penalty", lambda *_args, **_kwargs: 1.0, raising=False)

    trade = builder.build(_base_market_data(option_ltp=100.0), quick_mode=False, allow_fallbacks=False, allow_baseline=False)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == trade.strategy
    assert row["confidence_model_raw"] == 0.52
    assert row["confidence_after_soft_veto"] == trade.confidence_after_soft_veto
    assert row["confidence_raw_gate_threshold"] == 0.44
    assert abs(float(row["confidence_final_gate_threshold"]) - 0.31) < 0.011
