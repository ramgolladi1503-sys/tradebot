import json

from config import config as cfg
from core import market_data as md


def test_sim_index_fresh_ltp_missing_depth_is_missing_not_stale(monkeypatch):
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5, raising=False)
    out = md._classify_index_feed_health(
        symbol="NIFTY",
        execution_mode="SIM",
        now_epoch=1_000.0,
        ltp=25_000.0,
        ltp_ts_epoch=999.7,
        quote_ok=False,
        quote_source="missing_depth",
        quote_ts_epoch=None,
    )
    assert out["state"] == "MISSING"
    assert out["ok"] is True
    assert out["depth_required"] is False
    assert out["stale_reasons"] == []
    assert "depth_missing" in out["missing_reasons"]


def test_live_index_fresh_ltp_missing_depth_blocks_not_stale_and_logs_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "SLA_MAX_LTP_AGE_SEC", 2.5, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    md._LIVE_QUOTE_ERROR_LAST_TS.clear()

    out = md._classify_index_feed_health(
        symbol="NIFTY",
        execution_mode="LIVE",
        now_epoch=2_000.0,
        ltp=25_100.0,
        ltp_ts_epoch=1_999.8,
        quote_ok=False,
        quote_source="missing_depth",
        quote_ts_epoch=None,
    )
    assert out["state"] == "MISSING"
    assert out["ok"] is False
    assert out["depth_required"] is True
    assert out["stale_reasons"] == []

    md._log_index_bidask_missing("NIFTY", source="ws")
    p = tmp_path / "logs" / "live_quote_errors.jsonl"
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    assert rows[-1]["event_code"] == "index_bidask_missing"
    assert rows[-1]["category"] == "missing"
