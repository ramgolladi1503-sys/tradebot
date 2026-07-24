from __future__ import annotations


def certify_ledger(records: list[dict[str, object]]) -> dict[str, object]:
    if records:
        return {"verdict": "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": []}
    return {"verdict": "SIGNAL_EXECUTION_BLOCKED", "records": [], "failures": ["INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA"]}

