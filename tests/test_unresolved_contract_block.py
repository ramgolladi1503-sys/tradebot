import json
from pathlib import Path

from config import config as cfg
from strategies.trade_builder import TradeBuilder


class _PredictorStub:
    def predict_confidence(self, _feats):
        return 0.9


def _load_rows(path: Path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_unresolved_contract_blocks_without_levels(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "DESK_ID", "DEFAULT", raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "PAPER", raising=False)
    monkeypatch.setattr(cfg, "PAPER_STRICT_MODE", False, raising=False)
    monkeypatch.setattr(cfg, "ORB_BIAS_LOCK", False, raising=False)
    monkeypatch.setattr(cfg, "HTF_ALIGN_REQUIRED", False, raising=False)

    builder = TradeBuilder(predictor=_PredictorStub())
    monkeypatch.setattr(builder, "_apply_lifecycle_gate", lambda *_args, **_kwargs: (True, "ok"))
    monkeypatch.setattr(builder, "_apply_decay_gate", lambda *_args, **_kwargs: (True, None, 1.0, None))
    monkeypatch.setattr(
        builder,
        "_signal_for_symbol",
        lambda *_args, **_kwargs: {
            "direction": "BUY_CALL",
            "reason": "unit_test_signal",
            "score": 0.9,
            "regime_day": "TREND",
        },
    )

    trade = builder.build(
        {
            "symbol": "BANKNIFTY",
            "valid": True,
            "ltp": None,
            "quote_age_sec": None,
            "instrument": "OPT",
            "option_chain": [],
            "chain_source": "synthetic",
            "quote_ok": False,
            "bid": None,
            "ask": None,
        },
        quick_mode=True,
        allow_fallbacks=True,
        allow_baseline=True,
    )

    assert trade is None
    blocked_path = desk_log_dir / "blocked_candidates.jsonl"
    rows = _load_rows(blocked_path)
    assert rows
    last = rows[-1]
    assert last["reason_code"] == "unresolved_contract"
    assert last.get("derived_levels") is False
    assert last.get("stop") is None
    assert last.get("target") is None
