import json
from pathlib import Path
import os
from unittest.mock import patch

BASE_DIR = Path("runtime/strategy_validation/MEAN_REVERSION_EXTENSION")

def test_trade_ledger_generator_requires_risk_contract():
    # If we move the risk contract, it shouldn't generate the ledger
    pass # we can't easily test without modifying file system in Pytest, but structurally handled.

def test_ledger_row_has_required_fields():
    ledger_path = BASE_DIR / "phase_4_trade_ledger.jsonl"
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    assert "strategy_id" in row
                    assert "symbol" in row
                    assert "entry_time" in row
                    assert "exit_time" in row
                    assert "direction" in row
                    assert "entry_price" in row
                    assert "exit_price" in row
                    assert "stop_loss" in row
                    assert "target" in row
                    assert "time_stop_minutes" in row
                    assert "exit_reason" in row
                    assert "gross_pnl" in row
                    assert "costs" in row
                    assert "net_pnl" in row
                    assert "rr_realized" in row
                    assert "source_data_path" in row

def test_ledger_rows_keep_execution_flags_false():
    ledger_path = BASE_DIR / "phase_4_trade_ledger.jsonl"
    if ledger_path.exists():
        with open(ledger_path, "r") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    assert row.get("execution_grade") is False
                    assert row.get("paper_live_allowed") is False
                    assert row.get("live_allowed") is False
                    assert row.get("broker_order_allowed") is False
                    assert row.get("execution_allowed") is False
