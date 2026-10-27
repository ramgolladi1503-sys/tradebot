"""Unit tests for DualIndexShadowAdapter.

Verifies:
1. Adapter processes market snapshot safely without order action.
2. Invariant fields (read_only=True, is_order_action=False, broker_api_called=False) are preserved.
3. Shadow JSONL logging works deterministically.
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import pytest

from core.analytics.dual_index_shadow_adapter import DualIndexShadowAdapter, ShadowEvaluationRecord
from strategies.dual_index_regime_momentum import DualIndexRegimeInput, STRATEGY_ID

IST = ZoneInfo("Asia/Kolkata")


def test_shadow_adapter_records_observation(tmp_path: Path):
    adapter = DualIndexShadowAdapter(output_dir=tmp_path)
    eval_time = datetime(2026, 10, 22, 9, 22, 0, tzinfo=IST)
    inp = DualIndexRegimeInput(
        symbol="NIFTY",
        nifty_open=25200.0,
        nifty_prev_close=25000.0,
        sensex_open=81800.0,
        sensex_prev_close=81200.0,
        evaluation_time=eval_time,
        current_ltp=25210.0,
    )

    record = adapter.record_shadow_observation(inp)
    assert record.decision == "ENTER_LONG"
    assert record.read_only is True
    assert record.is_order_action is False
    assert record.broker_api_called is False

    # Check written file
    log_file = tmp_path / "dual_index_regime_shadow.jsonl"
    assert log_file.exists()
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["strategy_id"] == STRATEGY_ID
    assert data["read_only"] is True
    assert data["is_order_action"] is False
    assert data["broker_api_called"] is False
