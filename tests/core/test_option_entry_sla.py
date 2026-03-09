from core.option_entry import get_option_ltp_sla_sec, validate_live_entry
from config import config as cfg


def test_live_sla_remains_strict():
    assert get_option_ltp_sla_sec("LIVE", 2.0) == 2.0


def test_paper_sla_relaxed(monkeypatch):
    monkeypatch.setattr(cfg, "OFFHOURS_SLA_MAX_LTP_AGE_SEC", 900.0, raising=False)
    assert get_option_ltp_sla_sec("PAPER", 2.0) == 900.0


def test_validate_live_entry_uses_mode_based_sla(monkeypatch):
    monkeypatch.delenv("PAPER_OPTION_LTP_SLA_SEC", raising=False)

    live_out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=104.1,
        mode="LIVE",
        market_open=True,
        segment="NSE_FNO",
    )
    assert live_out["valid"] is False
    assert live_out["entry_status"] == "STALE_OPTION_LTP"

    paper_out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=104.1,
        mode="PAPER",
    )
    assert paper_out["valid"] is True
    assert paper_out["entry_status"] == "OK"


def test_validate_live_entry_clamps_live_sla_to_canonical_limit(monkeypatch):
    monkeypatch.setattr(cfg, "OPTION_LTP_SLA_SEC", 8.0, raising=False)
    monkeypatch.setattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5, raising=False)

    out_4_1 = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=104.1,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        segment="NSE_FNO",
    )
    assert out_4_1["valid"] is False
    assert out_4_1["entry_status"] == "STALE_OPTION_LTP"

    out_6_0 = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=106.0,
        mode="LIVE",
        allow_stale_quotes=False,
        market_open=True,
        segment="NSE_FNO",
    )
    assert out_6_0["valid"] is False
    assert out_6_0["entry_status"] == "STALE_OPTION_LTP"
