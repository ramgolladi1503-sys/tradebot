from __future__ import annotations

import json
from types import SimpleNamespace

import core.execution.execution_audit as execution_audit


def _trade() -> SimpleNamespace:
    return SimpleNamespace(
        trade_id="T-AUDIT-1",
        symbol="NIFTY",
        strategy_id="zero_hero",
        strategy_name="ZERO_HERO",
        entry=72.5,
        display_entry=72.5,
        execution_entry=72.8,
        hard_blockers=["NO_TOKEN"],
        soft_penalties=["PRICE_MISMATCH"],
        warnings=["DISPLAY_ENTRY_FALLBACK"],
        blockers=["NO_TOKEN", "PRICE_MISMATCH", "DISPLAY_ENTRY_FALLBACK"],
        execution_status="advisory_only",
        readiness="ADVISORY_ONLY",
    )


def test_append_execution_audit_event_writes_expected_fields(tmp_path, monkeypatch):
    logs_root = tmp_path / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(execution_audit, "logs_dir", lambda: logs_root)

    event = execution_audit.append_execution_audit_event(
        trade=_trade(),
        order_action="abort",
        guard_result={"execution_allowed": False, "reasons": ["spread_too_wide"]},
        broker_response={"reason_if_aborted": "spread_too_wide"},
        reason="spread_too_wide",
        ts_epoch=1_700_000_100.0,
    )

    assert event["trade_id"] == "T-AUDIT-1"
    assert event["symbol"] == "NIFTY"
    assert event["strategy_id"] == "zero_hero"
    assert event["display_entry"] == 72.5
    assert event["execution_entry"] == 72.8
    assert event["blocker_state"]["hard_blockers"] == ["NO_TOKEN"]
    assert event["guard_result"]["reasons"] == ["spread_too_wide"]
    latest = json.loads((logs_root / "execution_audit_latest.json").read_text(encoding="utf-8"))
    assert latest["order_action"] == "abort"
    rows = (logs_root / "execution_audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["reason"] == "spread_too_wide"
