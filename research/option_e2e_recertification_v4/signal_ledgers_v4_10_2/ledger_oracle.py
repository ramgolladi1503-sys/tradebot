from __future__ import annotations


def certify_ledger(records: list[dict[str, object]], contract_report: dict[str, object] | None = None) -> dict[str, object]:
    if contract_report and contract_report.get("valid") is False:
        return {
            "verdict": "SIGNAL_SOURCE_BLOCKED_WITH_EXHAUSTIVE_EVIDENCE",
            "records": records,
            "failures": list(contract_report.get("failures", [])),
        }
    if records:
        return {"verdict": "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": []}
    return {
        "verdict": "SIGNAL_EXECUTION_BLOCKED_WITH_EXACT_EXECUTION_EVIDENCE",
        "records": [],
        "failures": ["INSUFFICIENT_HISTORICAL_DATA_FOR_BACKTEST_OR_WFA"],
    }
