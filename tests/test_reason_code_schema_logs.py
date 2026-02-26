from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import config as cfg
from core import market_data
from core.orchestrator_parts.decisions import log_identity_error
from core.reject_logger import append_reject_reasons


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _assert_reason_code(path: Path, *, message: str) -> None:
    rows = _rows(path)
    assert rows, message
    row = rows[-1]
    code = str(row.get("reason_code") or "").strip()
    assert code, f"missing reason_code in {path}"


def test_reason_code_present_across_reject_emitters(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reject_path = tmp_path / "logs" / "reject_reasons.jsonl"
    monkeypatch.setattr(cfg, "REJECT_REASONS_LOG_PATH", str(reject_path), raising=False)

    append_reject_reasons(
        symbol="NIFTY",
        strategy="S1",
        reasons=["no_signal"],
        mode="PAPER",
        source="schema_test",
    )
    _assert_reason_code(reject_path, message="reject_reasons.jsonl should have at least one row")
    reject_row = _rows(reject_path)[-1]
    assert reject_row["reason_code"] == "no_signal"

    market_data._LIVE_QUOTE_ERROR_LAST_TS.clear()
    monkeypatch.setattr(market_data, "now_utc_epoch", lambda: 1_000.0)
    monkeypatch.setattr(
        market_data,
        "now_ist",
        lambda: datetime(2026, 2, 22, 0, 0, 0, tzinfo=timezone.utc),
    )
    market_data._append_live_quote_error(
        event_code="index_bidask_missing",
        symbol="NIFTY",
        category="missing",
        source="unit",
        details={"hint": "depth_missing"},
    )
    live_path = tmp_path / "logs" / "live_quote_errors.jsonl"
    _assert_reason_code(live_path, message="live_quote_errors.jsonl should have at least one row")
    live_row = _rows(live_path)[-1]
    assert live_row["reason_code"] == live_row["event_code"]

    market_data._INSUFFICIENT_OHLC_WARNED.clear()
    market_data._log_insufficient_ohlc_warning(
        symbol="NIFTY",
        bars_count=0,
        min_bars=30,
        reason="HIST_FETCH_FAILED",
        detail="kite_api_unavailable",
    )
    warn_path = tmp_path / "logs" / "market_data_warnings.jsonl"
    _assert_reason_code(warn_path, message="market_data_warnings.jsonl should have at least one row")
    warn_row = _rows(warn_path)[-1]
    assert warn_row["reason_code"] == warn_row["reason"]

    log_identity_error(
        None,
        {
            "trade_id": "T-1",
            "symbol": "NIFTY",
            "instrument_type": "OPT",
            "expiry": "2026-02-26",
            "strike": 25000,
            "right": "CE",
        },
        {"reason": "missing_contract_fields"},
    )
    ident_path = tmp_path / "logs" / "trade_identity_errors.jsonl"
    _assert_reason_code(ident_path, message="trade_identity_errors.jsonl should have at least one row")
    ident_row = _rows(ident_path)[-1]
    assert ident_row["reason_code"] == "missing_contract_fields"
