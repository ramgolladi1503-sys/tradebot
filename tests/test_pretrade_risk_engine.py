from config import config as cfg
from core.pretrade_risk_engine import PreTradeRiskEngine, PreTradeRiskRequest


def _engine(monkeypatch, tmp_path, **overrides):
    db_path = tmp_path / "pretrade_risk.db"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path), raising=False)
    defaults = {
        "PRETRADE_RISK_ENABLE": True,
        "PRETRADE_MARGIN_BUFFER_PCT": 0.0,
        "PRETRADE_MAX_EXPOSURE_PER_INSTRUMENT": 100.0,
        "PRETRADE_MAX_DAILY_LOSS": 100.0,
        "PRETRADE_MAX_TRADES_PER_MINUTE": 2,
        "PRETRADE_MAX_CORRELATED_EXPOSURE": 100.0,
        "PRETRADE_DUPLICATE_WINDOW_SEC": 300.0,
        "PRETRADE_CORRELATION_THRESHOLD": 0.75,
        "PRETRADE_REQUIRE_MARGIN_DATA": False,
        "PRETRADE_REQUIRE_DAILY_LOSS_DATA": False,
    }
    defaults.update(overrides)
    for key, value in defaults.items():
        monkeypatch.setattr(cfg, key, value, raising=False)
    return PreTradeRiskEngine(db_path=str(db_path), now_fn=lambda: 1000.0)


def _request(signal_id="SIG-1", instrument="NIFTY", side="BUY", exposure=10.0):
    return PreTradeRiskRequest(
        signal_id=signal_id,
        instrument=instrument,
        side=side,
        quantity=1.0,
        timestamp=1000.0,
        exposure=exposure,
        margin_required=exposure,
    )


def test_rejects_insufficient_margin(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path)
    decision = engine.evaluate(
        _request(),
        context={"margin_available": 5.0, "margin_required": 10.0},
    )
    assert decision.allowed is False
    assert decision.reason_code == "INSUFFICIENT_MARGIN"


def test_rejects_max_exposure_per_instrument(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path)
    decision = engine.evaluate(
        _request(exposure=30.0),
        context={"current_exposure_by_instrument": {"NIFTY": 80.0}},
    )
    assert decision.allowed is False
    assert decision.reason_code == "MAX_EXPOSURE_PER_INSTRUMENT"


def test_rejects_max_daily_loss(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path)
    decision = engine.evaluate(
        _request(),
        context={"daily_loss": 120.0},
    )
    assert decision.allowed is False
    assert decision.reason_code == "MAX_DAILY_LOSS"


def test_rejects_max_trades_per_minute(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path, PRETRADE_MAX_TRADES_PER_MINUTE=1)
    request = _request(signal_id="SIG-A")
    engine.record_decision(request, accepted=True, reason_code="ACCEPTED", order_id="OID-A", now_epoch=995.0)
    decision = engine.evaluate(_request(signal_id="SIG-B"))
    assert decision.allowed is False
    assert decision.reason_code == "MAX_TRADES_PER_MINUTE"


def test_rejects_correlated_exposure_limit(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path, PRETRADE_MAX_CORRELATED_EXPOSURE=100.0)
    decision = engine.evaluate(
        _request(exposure=30.0),
        context={
            "current_exposure_by_instrument": {"BANKNIFTY": 80.0},
            "correlations": {("NIFTY", "BANKNIFTY"): 0.9},
            "correlation_threshold": 0.8,
        },
    )
    assert decision.allowed is False
    assert decision.reason_code == "CORRELATED_EXPOSURE_LIMIT"


def test_rejects_duplicate_signal(monkeypatch, tmp_path):
    engine = _engine(monkeypatch, tmp_path)
    req = _request(signal_id="SIG-DUP")
    engine.record_decision(req, accepted=True, reason_code="ACCEPTED", order_id="OID-1", now_epoch=990.0)
    decision = engine.evaluate(req, context={"now_epoch": 1000.0})
    assert decision.allowed is False
    assert decision.reason_code == "DUPLICATE_SIGNAL"

