from __future__ import annotations

from dataclasses import asdict
import json

from config import config as cfg
from core import review_queue
from core.trade_schema import build_instrument_id
from strategies.trade_builder import TradeBuilder


def _market_data(symbol="BANKNIFTY", ltp=60000.0, change=200.0, atr=100.0):
    expiry = "2026-03-06"
    chain = [
        {
            "type": "CE",
            "strike": 60000,
            "ltp": 50.0,
            "bid": 49.0,
            "ask": 51.0,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR60000CE",
            "instrument_token": 111,
        },
        {
            "type": "CE",
            "strike": 60600,
            "ltp": 8.0,
            "bid": 7.5,
            "ask": 8.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR60600CE",
            "instrument_token": 112,
        },
        {
            "type": "CE",
            "strike": 61200,
            "ltp": 7.0,
            "bid": 6.5,
            "ask": 7.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR61200CE",
            "instrument_token": 113,
        },
        {
            "type": "CE",
            "strike": 61800,
            "ltp": 6.0,
            "bid": 5.5,
            "ask": 6.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR61800CE",
            "instrument_token": 114,
        },
        {
            "type": "PE",
            "strike": 58800,
            "ltp": 9.0,
            "bid": 8.5,
            "ask": 9.5,
            "expiry": expiry,
            "tradingsymbol": "BANKNIFTY26MAR58800PE",
            "instrument_token": 211,
        },
    ]
    return {
        "symbol": symbol,
        "ltp": ltp,
        "atr": atr,
        "ltp_change_window": change,
        "regime": "TREND",
        "day_type": "TREND_DAY",
        "market_open": False,
        "quote_age_sec": 0,
        "option_chain": chain,
        "chain_source": "synthetic_offhours",
        "market_context": {"execution_mode": "PAPER", "market_open": False},
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


def test_zero_to_hero_generation_otm(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MIN", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MAX", 0.02, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)

    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is not None
    assert trade.option_type == "CE"
    assert trade.strike >= md["ltp"] * 1.01
    assert trade.strike <= md["ltp"] * 1.02


def test_zero_to_hero_paper_only(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    tb = TradeBuilder()
    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is None


def test_zero_to_hero_not_executable(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)

    md = _market_data()
    trade = tb.build_zero_hero(md)
    assert trade is not None
    assert trade.execution_allowed is False
    assert trade.planning_only is True


def test_zero_to_hero_applies_trigger_entry_price(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MIN", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MAX", 0.02, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)
    monkeypatch.setattr(tb, "_option_executable_price", lambda opt, side="BUY": (51.0, "ask"))
    monkeypatch.setattr(tb, "_apply_entry_trigger", lambda price, side="BUY", quick_mode=True: (price + 2.0, "BUY_ABOVE", price))

    trade = tb.build_zero_hero(_market_data())

    assert trade is not None
    assert round(float(trade.entry_ref_price), 2) == 51.00
    assert round(float(trade.entry_price), 2) == 53.00
    assert trade.entry_condition == "BUY_ABOVE"
    assert float(trade.target) > float(trade.entry_price) > float(trade.stop_loss)


def test_zero_to_hero_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_REGIMES", ["TREND", "EVENT"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MIN", 0.01, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_OTM_PCT_MAX", 0.02, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_LOW", 0.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_PCT_HIGH", 1.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_PREMIUM_MIN_ROWS", 1, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *args, **kwargs: True, raising=False)

    trade = tb.build_zero_hero(_market_data())

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == trade.strategy
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_after_soft_veto"] == trade.confidence_after_soft_veto
    assert row["confidence_penalty_soft_veto_total"] == 0.0


def test_zero_to_hero_prefers_expiry_day_path_when_available(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_TO_HERO_ALLOWED_MODES", ["PAPER"], raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_ENABLE", True, raising=False)

    tb = TradeBuilder()
    called = {"expiry": 0}

    def _expiry_builder(market_data, debug_reasons=False):
        called["expiry"] += 1
        market_data["zero_hero_diagnostics"] = {
            "zero_hero_considered": 2,
            "zero_hero_rejected_reason": None,
            "zero_hero_selected_premium_band": {"low": 5.0, "high": 40.0, "source": "expiry_config"},
            "zero_hero_activation_window": {"variant": "expiry_day", "minutes_since_open": 35},
        }
        return type(
            "T",
            (),
            {
                "source_flags": {},
                "option_type": "CE",
                "execution_allowed": False,
                "planning_only": True,
            },
        )()

    monkeypatch.setattr(tb, "_is_expiry_day_for_symbol", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(tb, "_build_zero_hero_expiry", _expiry_builder)

    md = _market_data()
    md["minutes_since_open"] = 35
    trade = tb.build_zero_hero(md)

    assert trade is not None
    assert called["expiry"] == 1
    assert trade.source_flags["zero_hero_variant"] == "expiry_day"


def test_zero_hero_expiry_survives_moderate_imperfection(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", 90, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN", 150, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO", 0.65, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SPREAD_HARD_PCT", 0.45, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_IVCRUSH_MIN", 0.20, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", 6.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS", 1.5, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN", 0.08, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO", 0.20, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(tb, "_apply_alpha_ensemble", lambda confidence, *_args, **_kwargs: (confidence, None, None, 1.0))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda data, _ctx: (data["ltp"], "ltp", True, None))
    monkeypatch.setattr(tb, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-03-06")
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": expiry or "2026-03-06",
            "tradingsymbol": f"{symbol}TEST{int(strike)}{opt_type}",
            "instrument_token": 555001,
        },
    )
    monkeypatch.setattr(
        tb,
        "_identity_fields",
        lambda symbol, instrument, expiry, strike, right, qty_lots: (
            "OPT",
            build_instrument_id(symbol, instrument, expiry, strike, right),
            15,
            None,
        ),
    )
    monkeypatch.setattr(
        tb,
        "trade_intent_flags",
        lambda *_args, **_kwargs: {
            "tradable": False,
            "tradable_reasons_blocking": [],
            "planning_only": True,
            "execution_allowed": False,
            "execution_reason": "PAPER_ONLY",
            "source_flags": {},
        },
    )
    monkeypatch.setattr(tb, "_option_executable_price", lambda opt, side="BUY": (float(opt["ltp"]), "ltp"))
    monkeypatch.setattr(tb, "_apply_entry_trigger", lambda price, side="BUY", quick_mode=True: (price, "MARKET", price))
    monkeypatch.setattr(tb, "_decorate_trade_context", lambda trade, _data, _confidence: trade)
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *_args, **_kwargs: False, raising=False)

    market_data = {
        "symbol": "BANKNIFTY",
        "ltp": 60000.0,
        "atr": 100.0,
        "vwap": 59990.0,
        "ltp_change_window": 6.0,
        "minutes_since_open": 100,
        "orb_bias": "PENDING",
        "day_type": "EXPIRY_DAY",
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 1.0,
        "market_context": {"execution_mode": "PAPER", "market_open": True},
        "option_chain": [
            {
                "type": "CE",
                "strike": 60200,
                "ltp": 4.5,
                "bid": 4.1,
                "ask": 5.2,
                "delta": 0.18,
                "iv": 0.19,
                "time_to_expiry_hrs": 6.5,
                "volume": 180,
                "expiry": "2026-03-06",
                "tradingsymbol": "BANKNIFTYTEST60200CE",
                "instrument_token": 555001,
            }
        ],
    }

    trade = tb._build_zero_hero_expiry(market_data)

    assert trade is not None
    assert trade.option_type == "CE"
    assert trade.source_flags["zero_hero_expiry"] is True
    assert "premium_soft_band" in trade.source_flags["candidate_soft_flags"]
    assert "spread_soft_fail" in trade.source_flags["candidate_soft_flags"]
    assert "delta_soft_fail" in trade.source_flags["candidate_soft_flags"]
    assert "iv_soft_fail" in trade.source_flags["candidate_soft_flags"]
    assert trade.source_flags["zero_hero_considered"] == 1
    assert trade.source_flags["zero_hero_selected_premium_band"]["source"] == "expiry_config"
    assert trade.source_flags["zero_hero_activation_window"]["variant"] == "expiry_day"
    stats = market_data["strategy_debug"]["zero_hero_expiry"]
    assert stats["candidates_considered"] == 1
    assert stats["candidates_scored"] == 1
    diag = market_data["zero_hero_diagnostics"]
    assert diag["zero_hero_considered"] == 1
    assert diag["zero_hero_rejected_reason"] is None
    assert diag["zero_hero_selected_premium_band"]["source"] == "expiry_config"
    assert diag["zero_hero_activation_window"]["soft_cutoff_min"] == 90


def test_zero_hero_expiry_serializes_staged_confidence_fields(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", 90, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN", 150, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO", 0.65, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SPREAD_HARD_PCT", 0.45, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_IVCRUSH_MIN", 0.20, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", 6.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS", 1.5, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN", 0.08, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO", 0.20, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(tb, "_apply_alpha_ensemble", lambda confidence, *_args, **_kwargs: (confidence, None, None, 1.0))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda data, _ctx: (data["ltp"], "ltp", True, None))
    monkeypatch.setattr(tb, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-03-06")
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": expiry or "2026-03-06",
            "tradingsymbol": f"{symbol}TEST{int(strike)}{opt_type}",
            "instrument_token": 555001,
        },
    )
    monkeypatch.setattr(
        tb,
        "_identity_fields",
        lambda symbol, instrument, expiry, strike, right, qty_lots: (
            "OPT",
            build_instrument_id(symbol, instrument, expiry, strike, right),
            15,
            None,
        ),
    )
    monkeypatch.setattr(
        tb,
        "trade_intent_flags",
        lambda *_args, **_kwargs: {
            "tradable": False,
            "tradable_reasons_blocking": [],
            "planning_only": True,
            "execution_allowed": False,
            "execution_reason": "PAPER_ONLY",
            "source_flags": {},
        },
    )
    monkeypatch.setattr(tb, "_option_executable_price", lambda opt, side="BUY": (float(opt["ltp"]), "ltp"))
    monkeypatch.setattr(tb, "_apply_entry_trigger", lambda price, side="BUY", quick_mode=True: (price, "MARKET", price))
    monkeypatch.setattr(tb, "_decorate_trade_context", lambda trade, _data, _confidence: trade)
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *_args, **_kwargs: False, raising=False)

    market_data = {
        "symbol": "BANKNIFTY",
        "ltp": 60000.0,
        "atr": 100.0,
        "vwap": 59990.0,
        "ltp_change_window": 6.0,
        "minutes_since_open": 100,
        "orb_bias": "PENDING",
        "day_type": "EXPIRY_DAY",
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 1.0,
        "market_context": {"execution_mode": "PAPER", "market_open": True},
        "option_chain": [
            {
                "type": "CE",
                "strike": 60200,
                "ltp": 4.5,
                "bid": 4.1,
                "ask": 5.2,
                "delta": 0.18,
                "iv": 0.19,
                "time_to_expiry_hrs": 6.5,
                "volume": 180,
                "expiry": "2026-03-06",
                "tradingsymbol": "BANKNIFTYTEST60200CE",
                "instrument_token": 555001,
            }
        ],
    }

    trade = tb._build_zero_hero_expiry(market_data)

    assert trade is not None
    row = _serialize_trade_row(tmp_path, monkeypatch, trade)
    _assert_staged_confidence_fields_present(row)
    assert row["strategy"] == "ZERO_HERO_EXPIRY"
    assert row["confidence_model_raw"] == trade.confidence_model_raw
    assert row["confidence_before_soft_veto"] == trade.confidence_before_soft_veto
    assert row["confidence_after_soft_veto"] == trade.confidence_after_soft_veto


def test_zero_hero_expiry_applies_trigger_entry_price(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_CUTOFF_MIN", 90, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_TIME_HARD_CUTOFF_MIN", 150, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_MOMENTUM_RATIO", 0.65, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SPREAD_HARD_PCT", 0.45, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_IVCRUSH_MIN", 0.20, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_TIME_TO_EXPIRY_MAX_HRS", 6.0, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_TTE_MARGIN_HRS", 1.5, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_SOFT_DELTA_MARGIN", 0.08, raising=False)
    monkeypatch.setattr(cfg, "ZERO_HERO_EXPIRY_PREMIUM_SOFT_MARGIN_RATIO", 0.20, raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(tb, "_apply_alpha_ensemble", lambda confidence, *_args, **_kwargs: (confidence, None, None, 1.0))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda data, _ctx: (data["ltp"], "ltp", True, None))
    monkeypatch.setattr(tb, "_resolve_expiry_for_symbol", lambda *_args, **_kwargs: "2026-03-06")
    monkeypatch.setattr(
        tb,
        "_resolve_option_contract",
        lambda symbol, strike, opt_type, expiry, market_data: {
            "expiry": expiry or "2026-03-06",
            "tradingsymbol": f"{symbol}TEST{int(strike)}{opt_type}",
            "instrument_token": 555001,
        },
    )
    monkeypatch.setattr(
        tb,
        "_identity_fields",
        lambda symbol, instrument, expiry, strike, right, qty_lots: (
            "OPT",
            build_instrument_id(symbol, instrument, expiry, strike, right),
            15,
            None,
        ),
    )
    monkeypatch.setattr(
        tb,
        "trade_intent_flags",
        lambda *_args, **_kwargs: {
            "tradable": False,
            "tradable_reasons_blocking": [],
            "planning_only": True,
            "execution_allowed": False,
            "execution_reason": "PAPER_ONLY",
            "source_flags": {},
        },
    )
    monkeypatch.setattr(tb, "_option_executable_price", lambda opt, side="BUY": (5.2, "ask"))
    monkeypatch.setattr(tb, "_apply_entry_trigger", lambda price, side="BUY", quick_mode=True: (price + 1.5, "BUY_ABOVE", price))
    monkeypatch.setattr(tb, "_decorate_trade_context", lambda trade, _data, _confidence: trade)
    monkeypatch.setattr(tb.execution, "spread_ok", lambda *_args, **_kwargs: False, raising=False)

    market_data = {
        "symbol": "BANKNIFTY",
        "ltp": 60000.0,
        "atr": 100.0,
        "vwap": 59990.0,
        "ltp_change_window": 6.0,
        "minutes_since_open": 100,
        "orb_bias": "PENDING",
        "day_type": "EXPIRY_DAY",
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 1.0,
        "market_context": {"execution_mode": "PAPER", "market_open": True},
        "option_chain": [
            {
                "type": "CE",
                "strike": 60200,
                "ltp": 4.5,
                "bid": 4.1,
                "ask": 5.2,
                "delta": 0.18,
                "iv": 0.19,
                "time_to_expiry_hrs": 6.5,
                "volume": 180,
                "expiry": "2026-03-06",
                "tradingsymbol": "BANKNIFTYTEST60200CE",
                "instrument_token": 555001,
            }
        ],
    }

    trade = tb._build_zero_hero_expiry(market_data)

    assert trade is not None
    assert round(float(trade.entry_ref_price), 2) == 5.20
    assert round(float(trade.entry_price), 2) == 6.70
    assert trade.entry_condition == "BUY_ABOVE"
    assert float(trade.target) > float(trade.entry_price) > float(trade.stop_loss)


def test_zero_hero_expiry_rejects_structurally_invalid_option(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    tb = TradeBuilder()
    monkeypatch.setattr(tb, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(tb, "_resolve_underlying_spot", lambda data, _ctx: (data["ltp"], "ltp", True, None))

    market_data = {
        "symbol": "BANKNIFTY",
        "ltp": 60000.0,
        "atr": 100.0,
        "vwap": 59990.0,
        "ltp_change_window": 10.0,
        "minutes_since_open": 30,
        "orb_bias": "UP",
        "day_type": "EXPIRY_DAY",
        "regime": "TREND",
        "market_open": True,
        "quote_age_sec": 1.0,
        "market_context": {"execution_mode": "PAPER", "market_open": True},
        "option_chain": [
            {
                "type": "CE",
                "strike": 60200,
                "ltp": 7.0,
                "bid": None,
                "ask": 8.0,
                "expiry": "2026-03-06",
            }
        ],
    }

    trade = tb._build_zero_hero_expiry(market_data)

    assert trade is None
    stats = market_data["strategy_debug"]["zero_hero_expiry"]
    assert stats["candidates_considered"] == 1
    assert stats["candidates_scored"] == 0
    assert stats["candidates_rejected_pre_score"] >= 1
    assert stats["rejection_reason_counts"]["partial_option_row"] >= 1
    diag = market_data["zero_hero_diagnostics"]
    assert diag["zero_hero_considered"] == 1
    assert diag["zero_hero_rejected_reason"] == "partial_option_row"
