import json
from pathlib import Path

def test_candidate_strategy_backtest():
    report_path = Path("runtime/strategy_validation/VWAP_RECLAIM/phase_4_report.json")
    if report_path.exists():
        with open(report_path, "r") as f:
            data = json.load(f)
        blockers = data.get("blockers", [])
        if "INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA" in blockers:
            assert data.get("passed") is False
            assert data.get("verdict") == "BLOCKED"
        assert "net_pnl" in data
        assert "max_drawdown" in data
        assert "win_rate" in data
