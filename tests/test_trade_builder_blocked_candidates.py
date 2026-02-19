import json
from pathlib import Path

from config import config as cfg
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    model_version = "stub"
    shadow_version = None

    def predict_confidence(self, _feats):
        return 0.9


def _load_blocked_rows(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def test_blocked_candidate_logged_for_missing_quote(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    trade = builder.build(
        {
            "symbol": "NIFTY",
            "valid": True,
            "ltp": 25000.0,
            "vwap": 24990.0,
            "atr": 20.0,
            "instrument": "OPT",
            "quote_ok": False,
            "bid": None,
            "ask": None,
            "index_quote_cache": {},
            "option_chain": [],
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    blocked_path = desk_log_dir / "blocked_candidates.jsonl"
    assert blocked_path.exists()
    rows = _load_blocked_rows(blocked_path)
    assert rows
    assert rows[-1]["reason_code"] == "missing_index_bid_ask"
    assert rows[-1]["stage"] == "trade_builder"
    assert rows[-1]["symbol"] == "NIFTY"


def test_blocked_candidate_logged_for_no_signal(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    monkeypatch.setattr(builder, "_signal_for_symbol", lambda *_args, **_kwargs: None)
    trade = builder.build(
        {
            "symbol": "NIFTY",
            "valid": True,
            "ltp": 25000.0,
            "vwap": 24990.0,
            "atr": 20.0,
            "instrument": "OPT",
            "chain_source": "live",
            "quote_ok": True,
            "bid": 24999.0,
            "ask": 25001.0,
            "option_chain": [],
        },
        quick_mode=False,
        allow_fallbacks=False,
        allow_baseline=False,
    )

    assert trade is None
    blocked_path = desk_log_dir / "blocked_candidates.jsonl"
    assert blocked_path.exists()
    rows = _load_blocked_rows(blocked_path)
    assert rows
    assert rows[-1]["reason_code"] == "no_signal"
    assert rows[-1]["stage"] == "trade_builder"
    assert rows[-1]["symbol"] == "NIFTY"
