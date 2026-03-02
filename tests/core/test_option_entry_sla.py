from core.option_entry import get_option_ltp_sla_sec, validate_live_entry


def test_live_sla_remains_strict():
    assert get_option_ltp_sla_sec("LIVE", 2.0) == 2.0


def test_paper_sla_relaxed(monkeypatch):
    monkeypatch.delenv("PAPER_OPTION_LTP_SLA_SEC", raising=False)
    assert get_option_ltp_sla_sec("PAPER", 2.0) == 6.0


def test_validate_live_entry_uses_mode_based_sla(monkeypatch):
    monkeypatch.delenv("PAPER_OPTION_LTP_SLA_SEC", raising=False)

    live_out = validate_live_entry(
        signal_price=100.0,
        current_ltp=100.0,
        ltp_ts_epoch=100.0,
        now_epoch=104.1,
        mode="LIVE",
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
