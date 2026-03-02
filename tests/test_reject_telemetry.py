import json
from pathlib import Path

import pytest

from config import config as cfg
from core.reject_telemetry import clear_reject_telemetry_memory, get_recent_reject_telemetry
from strategies.trade_builder import TradeBuilder


REQUIRED_REJECT_KEYS = {
    "timestamp_epoch_ms",
    "symbol",
    "strike",
    "trade_side",
    "reject_reason",
    "quote_age_sec",
    "spread_pct",
    "feed_state",
}


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            if not raw:
                continue
            rows.append(json.loads(raw))
    return rows


@pytest.mark.parametrize(
    "reason_code",
    [
        "no_signal",
        "spread_pct",
        "stale_option_quote",
        "missing_live_bidask",
    ],
)
def test_trade_builder_reject_telemetry_schema(monkeypatch, tmp_path, reason_code):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    telemetry_dir = desk_log_dir / "reject_telemetry"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_LOG_DIR", str(telemetry_dir), raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_MAX_IN_MEMORY", 200, raising=False)
    clear_reject_telemetry_memory()

    builder = TradeBuilder()
    builder._log_blocked_candidate(
        "NIFTY",
        reason_code,
        "unit_test_reject",
        market_data={
            "quote_age_sec": 1.7,
            "spread_pct": 0.012,
            "feed_state": "DEGRADED",
        },
        extra={
            "strike": 25000,
            "direction": "BUY_CALL",
        },
    )

    recent = get_recent_reject_telemetry(limit=50)
    assert recent
    top = recent[0]
    assert REQUIRED_REJECT_KEYS.issubset(set(top.keys()))
    assert top["symbol"] == "NIFTY"
    assert top["reject_reason"] == reason_code
    assert top["trade_side"] == "BUY_CALL"
    assert float(top["quote_age_sec"]) == pytest.approx(1.7)
    assert float(top["spread_pct"]) == pytest.approx(0.012)
    assert top["feed_state"] == "DEGRADED"


def test_trade_builder_reject_telemetry_daily_log_append(monkeypatch, tmp_path):
    desk_log_dir = tmp_path / "logs" / "desks" / "DEFAULT"
    telemetry_dir = desk_log_dir / "reject_telemetry"
    monkeypatch.setattr(cfg, "DESK_LOG_DIR", str(desk_log_dir), raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_LOG_DIR", str(telemetry_dir), raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_ENABLE", True, raising=False)
    monkeypatch.setattr(cfg, "REJECT_TELEMETRY_MAX_IN_MEMORY", 200, raising=False)
    clear_reject_telemetry_memory()

    builder = TradeBuilder()
    reasons = ["no_signal", "spread_pct", "stale_option_quote"]
    for idx, reason in enumerate(reasons):
        builder._log_blocked_candidate(
            "BANKNIFTY",
            reason,
            "unit_test_reject",
            market_data={
                "quote_age_sec": 0.5 + idx,
                "spread_pct": 0.01 + (idx * 0.001),
                "feed_state": "OK" if idx == 0 else "DEGRADED",
            },
            extra={
                "strike": 52000 + (idx * 100),
                "direction": "BUY_PUT",
            },
        )

    files = sorted(telemetry_dir.glob("rejects_*.jsonl"))
    assert files
    rows = _read_jsonl(files[-1])
    assert len(rows) == len(reasons)
    assert [row.get("reject_reason") for row in rows] == reasons
    assert all(REQUIRED_REJECT_KEYS.issubset(set(row.keys())) for row in rows)
