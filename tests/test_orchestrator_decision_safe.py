from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

from config import config as cfg
from core.orchestrator_parts.decisions import log_decision_safe


def _load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_log_decision_safe_logs_nontrade_event_without_instrument_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    reject_path = Path(cfg.LOGS_ROOT) / "reject_reasons.jsonl"
    monkeypatch.setattr(cfg, "REJECT_REASONS_LOG_PATH", str(reject_path), raising=False)

    event = {
        "trade_id": "DECISION-001",
        "symbol": "NIFTY",
        "strategy_id": None,
        "instrument_id": None,
        "veto_reasons": ["no_signal"],
        "mode": "PAPER",
        "gatekeeper_allowed": 0,
    }
    logged = []

    result = log_decision_safe(
        SimpleNamespace(),
        event,
        trade=None,
        log_decision_fn=lambda payload: logged.append(payload) or "logged-ok",
    )

    assert result == "logged-ok"
    assert len(logged) == 1
    assert logged[0]["trade_id"] == "DECISION-001"
    assert str(logged[0]["instrument_id"]).startswith("MISSING_CONTRACT::NIFTY:")
    assert "missing_contract_fields" in list(logged[0].get("veto_reasons") or [])

    rows = _load_jsonl(reject_path)
    assert rows
    reason_codes = [str(row.get("reason_code")) for row in rows]
    assert "no_signal" in reason_codes
    assert "missing_contract_fields" in reason_codes
    assert all(str(row.get("mode")) == "PAPER" for row in rows)
    assert not (Path(cfg.LOGS_ROOT) / "trade_identity_errors.jsonl").exists()


def test_log_decision_safe_persists_trade_event_with_fallback_instrument_id(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cfg, "LOGS_ROOT", str(tmp_path / "logs"), raising=False)
    reject_path = Path(cfg.LOGS_ROOT) / "reject_reasons.jsonl"
    monkeypatch.setattr(cfg, "REJECT_REASONS_LOG_PATH", str(reject_path), raising=False)

    trade = SimpleNamespace(
        trade_id="T-001",
        symbol="NIFTY",
        instrument_type="OPT",
        instrument="OPT",
        expiry="2026-02-26",
        strike=25000,
        right="CE",
        option_type="CE",
    )
    event = {
        "trade_id": "T-001",
        "symbol": "NIFTY",
        "strategy_id": "S1",
        "instrument_id": None,
        "veto_reasons": [],
        "mode": "LIVE",
        "gatekeeper_allowed": 1,
    }
    logged = []

    result = log_decision_safe(
        SimpleNamespace(),
        event,
        trade=trade,
        log_decision_fn=lambda payload: logged.append(payload) or "logged-ok",
    )

    assert result == "logged-ok"
    assert len(logged) == 1
    assert str(logged[0]["instrument_id"]).startswith("MISSING_CONTRACT::NIFTY:OPT:2026-02-26:25000:CE")
    assert "missing_contract_fields" in list(logged[0].get("veto_reasons") or [])
    identity_path = Path(cfg.LOGS_ROOT) / "trade_identity_errors.jsonl"
    assert identity_path.exists()
    rows = _load_jsonl(reject_path)
    assert any(str(row.get("reason_code")) == "missing_contract_fields" for row in rows)
