import json

from config import config as cfg
from core.feed_debug import get_feed_debug


def test_feed_debug_reads_snapshot(monkeypatch, tmp_path):
    logs_path = tmp_path / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    snapshot_path = logs_path / "feed_runtime_latest.json"
    now_epoch = 1_700_000_000.0
    snapshot_path.write_text(
        json.dumps(
            {
                "ts_epoch": now_epoch,
                "ws_connected": True,
                "subscribed_tokens_count": 73,
                "subscribed_tokens_count_by_symbol": {"NIFTY": 27},
                "subscribed_option_tokens_count": 26,
                "option_tokens_resolved_count_by_symbol": {"NIFTY": 26},
                "option_tokens_subscribed_count_by_symbol": {"NIFTY": 26},
                "option_ticks_received_count_by_symbol": {"NIFTY": 26},
                "last_option_tick_ts_by_symbol": {"NIFTY": now_epoch - 0.5},
                "option_feed_block_reason_by_symbol": {"NIFTY": "OK"},
                "option_last_tick_age_by_symbol": {"NIFTY": 0.5},
                "last_db_tick_epoch": now_epoch - 1.0,
                "last_db_tick_age_sec": 1.0,
                "last_ws_tick_epoch": now_epoch - 0.5,
                "restart_count_1h": 2,
                "stale_strikes": 0,
            }
        )
    )

    monkeypatch.setattr("core.feed_debug.logs_dir", lambda: logs_path)
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(tmp_path / "db.sqlite"), raising=False)
    monkeypatch.setattr("core.feed_debug._resolve_db_path", lambda: tmp_path / "db.sqlite")
    monkeypatch.setattr("core.feed_debug._token_resolution_stats", lambda: (False, 0))

    payload = get_feed_debug(now_epoch=now_epoch + 1.0)

    assert payload["ws_connected"] is True
    assert payload["subscribed_tokens_count"] == 73
    assert payload["subscribed_option_tokens_count"] == 26
    assert payload["option_tokens_subscribed_count_by_symbol"] == {"NIFTY": 26}
    assert payload["option_feed_block_reason_by_symbol"] == {"NIFTY": "OK"}
    assert payload["last_db_tick_epoch"] == now_epoch - 1.0
    assert payload["last_db_tick_age_sec"] == 1.0
