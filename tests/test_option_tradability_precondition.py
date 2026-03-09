from __future__ import annotations

import json
from pathlib import Path

from config import config as cfg
import strategies.trade_builder as trade_builder_module
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.95


def _base_option_row() -> dict:
    return {
        "type": "CE",
        "strike": 25000.0,
        "ltp": 101.0,
        "bid": 100.0,
        "ask": 102.0,
        "quote_ok": True,
        "quote_live": True,
        "quote_age_sec": 0.5,
        "quote_ts_epoch": 1772500000.0,
        "volume": 5000,
        "oi": 20000,
        "oi_change": 1000,
        "iv": 0.2,
        "iv_z": 0.0,
        "iv_skew": 0.0,
        "delta": 0.35,
        "moneyness": 0.0,
    }


def _base_market_data(option_row: dict) -> dict:
    return {
        "symbol": "NIFTY",
        "market_open": True,
        "valid": True,
        "ltp": 25000.0,
        "vwap": 24990.0,
        "atr": 20.0,
        "bias": "Bullish",
        "instrument": "OPT",
        "chain_source": "live",
        "quote_ok": True,
        "bid": 24999.0,
        "ask": 25001.0,
        "regime": "TREND",
        "regime_day": "TREND",
        "day_type": "TREND_DAY",
        "option_chain": [option_row],
    }


def _patch_builder(monkeypatch, builder: TradeBuilder) -> None:
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "TRADING_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)
    monkeypatch.setattr(cfg, "ALPHA_ENSEMBLE_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_AB_ENABLE", False, raising=False)
    monkeypatch.setattr(cfg, "ML_USE_ONLY_WITH_HISTORY", False, raising=False)
    monkeypatch.setattr(cfg, "ML_MIN_PROBA", 0.1, raising=False)
    monkeypatch.setattr(cfg, "TRADE_SCORE_MIN", 1.0, raising=False)
    monkeypatch.setattr(cfg, "MIN_RR", 0.1, raising=False)
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda *_args, **_kwargs: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.95,
            "regime_day": "TREND",
        },
        raising=True,
    )
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"), raising=True)
    monkeypatch.setattr(
        builder,
        "_apply_decay_gate",
        lambda _strategy_name, base_score=None, size_mult=1.0: (True, base_score, size_mult, None),
        raising=True,
    )
    monkeypatch.setattr(builder, "_validate_ml_features", lambda _feats: (True, "ok"), raising=True)
    monkeypatch.setattr(
        trade_builder_module,
        "compute_trade_score",
        lambda *args, **kwargs: {"score": 100.0, "alignment": 1.0},
        raising=True,
    )


def _read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw:
            continue
        out.append(json.loads(raw))
    return out


def test_missing_instrument_token_rejected_before_gating_and_not_logged_as_blocked_candidate(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "DESK_ID", "DEFAULT", raising=False)
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)

    telemetry_rows: list[dict] = []
    monkeypatch.setattr(
        trade_builder_module,
        "append_reject_telemetry",
        lambda payload: telemetry_rows.append(dict(payload)),
        raising=True,
    )
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-02",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": None,
            "instrument_id": "NIFTY|OPT|2026-03-02|25000|CE",
        },
        raising=True,
    )
    monkeypatch.setattr(
        builder,
        "_identity_fields",
        lambda *_args, **_kwargs: ("OPT", "NIFTY|OPT|2026-03-02|25000|CE", 1, None),
        raising=True,
    )

    md = _base_market_data(_base_option_row())
    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is None
    assert int(builder._scan_reject_counts.get("unresolved_contract", 0)) >= 1
    assert any(str(row.get("reject_reason")) == "unresolved_contract" for row in telemetry_rows)

    blocked_rows = _read_rows(desk_log_dir / "blocked_candidates.jsonl")
    assert all(str(row.get("reason_code")) != "unresolved_contract" for row in blocked_rows)


def test_synthetic_index_quote_source_rejected_with_no_option_quote_source(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    telemetry_rows: list[dict] = []
    monkeypatch.setattr(
        trade_builder_module,
        "append_reject_telemetry",
        lambda payload: telemetry_rows.append(dict(payload)),
        raising=True,
    )
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-02",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY|OPT|2026-03-02|25000|CE",
        },
        raising=True,
    )
    monkeypatch.setattr(
        builder,
        "_identity_fields",
        lambda *_args, **_kwargs: ("OPT", "NIFTY|OPT|2026-03-02|25000|CE", 1, None),
        raising=True,
    )
    row = _base_option_row()
    row["quote_source"] = "synthetic_index"
    row["option_ltp_source"] = None
    md = _base_market_data(row)
    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is None
    assert int(builder._scan_reject_counts.get("NO_OPTION_QUOTE_SOURCE", 0)) >= 1
    assert any(str(row.get("reject_reason")) == "NO_OPTION_QUOTE_SOURCE" for row in telemetry_rows)


def test_resolved_contract_and_fresh_option_tick_reaches_gating(monkeypatch):
    builder = TradeBuilder(predictor=_PredictorStub())
    _patch_builder(monkeypatch, builder)
    monkeypatch.setattr(
        builder,
        "_resolve_option_contract",
        lambda *_args, **_kwargs: {
            "expiry": "2026-03-02",
            "tradingsymbol": "NIFTY26MAR25000CE",
            "instrument_token": 123456,
            "instrument_id": "NIFTY|OPT|2026-03-02|25000|CE",
        },
        raising=True,
    )
    monkeypatch.setattr(
        builder,
        "_identity_fields",
        lambda *_args, **_kwargs: ("OPT", "NIFTY|OPT|2026-03-02|25000|CE", 1, None),
        raising=True,
    )
    row = _base_option_row()
    row["quote_source"] = "depth"
    row["option_ltp_source"] = "depth_ws"
    md = _base_market_data(row)
    trade = builder.build(md, quick_mode=False, allow_fallbacks=False, allow_baseline=False)
    assert trade is not None
    assert int(trade.instrument_token or 0) > 0
    assert str(getattr(trade, "option_ltp_source", "")).lower() in {"depth_ws", "depth"}
