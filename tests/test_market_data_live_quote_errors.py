import json
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg
from core import market_data


def test_append_live_quote_error_rate_limited(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 30.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()

    now_holder = {"value": 1_000.0}
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: float(now_holder["value"]))
    monkeypatch.setattr(
        market_data,
        "now_ist",
        lambda: datetime(2026, 2, 20, 0, 0, 0, tzinfo=timezone.utc),
    )

    market_data._append_live_quote_error(
        event_code="index_bidask_missing",
        symbol="NIFTY",
        category="missing",
        source="ws",
        details={"missing_fields": ["bid", "ask"]},
    )
    now_holder["value"] = 1_005.0
    market_data._append_live_quote_error(
        event_code="index_bidask_missing",
        symbol="NIFTY",
        category="missing",
        source="ws",
        details={"missing_fields": ["bid", "ask"]},
    )

    out_path = Path("logs/live_quote_errors.jsonl")
    assert out_path.exists()
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["event_code"] == "index_bidask_missing"
    assert row["category"] == "missing"
    assert row["symbol"] == "NIFTY"
    assert row["source"] == "ws"
    assert row["details"]["missing_fields"] == ["bid", "ask"]


def test_sim_index_missing_depth_does_not_append_live_quote_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "SIM", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()

    market_data._maybe_log_index_bidask_missing(
        "NIFTY",
        quote_ok=False,
        quote_source="missing_depth",
        ltp_source="live",
        market_open=True,
    )

    out_path = Path("logs/live_quote_errors.jsonl")
    if out_path.exists():
        rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert all(row.get("event_code") != "index_bidask_missing" for row in rows)
    else:
        assert not out_path.exists()


def test_live_index_missing_depth_appends_live_quote_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()

    market_data._maybe_log_index_bidask_missing(
        "NIFTY",
        quote_ok=False,
        quote_source="missing_depth",
        ltp_source="live",
        market_open=True,
    )

    out_path = Path("logs/live_quote_errors.jsonl")
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    row = rows[-1]
    assert row["event_code"] == "index_bidask_missing"
    assert row["category"] == "missing"
    assert row["details"]["mode"] == "LIVE"
    assert row["details"]["market_open"] is True
    assert row["details"]["quote_source"] == "missing_depth"
    assert row["details"]["ltp_source"] == "live"
    assert row["level"] == "ERROR"


def test_live_index_missing_depth_with_usable_ltp_logs_warn(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()

    market_data._maybe_log_index_bidask_missing(
        "NIFTY",
        quote_ok=False,
        quote_source="missing_depth",
        ltp_source="live",
        market_open=True,
        ltp=25000.0,
        ltp_age_sec=1.0,
    )

    out_path = Path("logs/live_quote_errors.jsonl")
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert rows
    row = rows[-1]
    assert row["event_code"] == "index_bidask_missing"
    assert row["level"] == "WARN"



def test_live_index_missing_depth_offhours_does_not_append_live_quote_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()

    market_data._maybe_log_index_bidask_missing(
        "NIFTY",
        quote_ok=False,
        quote_source="missing_depth",
        ltp_source="live",
        market_open=False,
    )

    out_path = Path("logs/live_quote_errors.jsonl")
    if not out_path.exists():
        return
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert all(row.get("event_code") != "index_bidask_missing" for row in rows)


def test_get_ltp_logs_kite_not_initialized_with_canonical_schema(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()
    market_data._DATA_CACHE.clear()
    market_data._LAST_GOOD_LTP.clear()

    monkeypatch.setattr(market_data, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)
    monkeypatch.setattr(market_data, "get_index_quote_snapshot", lambda symbol: None)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", None)
    monkeypatch.setattr(market_data.kite_client, "ltp", lambda keys: {})
    monkeypatch.setattr(market_data, "is_market_open_ist", lambda segment="NSE_FNO": True)

    market_data.get_ltp("RELIANCE")

    out_path = Path("logs/live_quote_errors.jsonl")
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kite_rows = [row for row in rows if row.get("event_code") == "kite_not_initialized"]
    assert kite_rows
    row = kite_rows[-1]
    assert row["category"] == "auth"
    assert row["symbol"] == "RELIANCE"
    assert isinstance(row.get("details"), dict)


def test_get_ltp_logs_ltp_fetch_failed_with_canonical_schema(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "KITE_USE_API", True, raising=False)
    monkeypatch.setattr(cfg, "EXECUTION_MODE", "LIVE", raising=False)
    monkeypatch.setattr(cfg, "REQUIRE_LIVE_QUOTES", True, raising=False)
    monkeypatch.setattr(cfg, "LIVE_QUOTE_ERROR_MIN_LOG_SEC", 0.0, raising=False)
    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()
    market_data._DATA_CACHE.clear()
    market_data._LAST_GOOD_LTP.clear()

    monkeypatch.setattr(market_data, "_refresh_index_quote_from_rest", lambda symbol, force=False: False)
    monkeypatch.setattr(market_data, "get_index_quote_snapshot", lambda symbol: None)
    monkeypatch.setattr(market_data.kite_client, "ensure", lambda: None)
    monkeypatch.setattr(market_data.kite_client, "kite", object())
    monkeypatch.setattr(market_data.kite_client, "ltp", lambda keys: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(market_data, "is_market_open_ist", lambda segment="NSE_FNO": True)

    market_data.get_ltp("NIFTY")

    out_path = Path("logs/live_quote_errors.jsonl")
    rows = [json.loads(line) for line in out_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    failed_rows = [row for row in rows if row.get("event_code") == "ltp_fetch_failed"]
    assert failed_rows
    row = failed_rows[-1]
    assert row["category"] == "exception"
    assert row["symbol"] == "NIFTY"
    assert row["source"] == "rest"
    assert isinstance(row.get("details"), dict)
