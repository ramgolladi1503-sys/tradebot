from __future__ import annotations

import json

import core.gpt_advisor as gpt_advisor


def test_save_advice_writes_under_logs_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(gpt_advisor, "logs_dir", lambda: tmp_path)

    gpt_advisor.save_advice(
        trade_id="trade-123",
        advice={"action": "wait", "confidence": 0.42},
        meta={"symbol": "NIFTY"},
    )

    advice_path = tmp_path / "gpt_advice.jsonl"
    assert advice_path.exists()
    lines = [ln for ln in advice_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["trade_id"] == "trade-123"
    assert payload["advice"]["action"] == "wait"
