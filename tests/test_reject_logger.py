from __future__ import annotations

import json

from config import config as cfg
from core.reject_logger import append_reject_reasons


def test_append_reject_reasons_writes_structured_rows(monkeypatch, tmp_path):
    reject_path = tmp_path / "logs" / "reject_reasons.jsonl"
    monkeypatch.setattr(cfg, "REJECT_REASONS_LOG_PATH", str(reject_path), raising=False)

    append_reject_reasons(
        symbol="nifty",
        strategy=None,
        reasons=[" bad_quote ", "", None, "BAD_QUOTE"],
        mode="paper",
        source="unit_test",
        extra={"scope": "replay"},
    )

    assert reject_path.exists()
    rows = [
        json.loads(line)
        for line in reject_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    assert row["symbol"] == "NIFTY"
    assert row["strategy"] == "UNKNOWN"
    assert row["reason"] == "bad_quote"
    assert row["reason_code"] == "bad_quote"
    assert row["mode"] == "PAPER"
    assert row["source"] == "unit_test"
    assert row["details"]["scope"] == "replay"


def test_append_reject_reasons_noop_when_reasons_empty(monkeypatch, tmp_path):
    reject_path = tmp_path / "logs" / "reject_reasons.jsonl"
    monkeypatch.setattr(cfg, "REJECT_REASONS_LOG_PATH", str(reject_path), raising=False)

    append_reject_reasons(
        symbol="NIFTY",
        strategy="S1",
        reasons=[],
        mode="SIM",
        source="unit_test",
    )

    assert not reject_path.exists()
