from __future__ import annotations


def certify_ledger(records):
    if not records:
        return {"verdict": "SIGNAL_RECOVERY_NOT_EXECUTED", "records": [], "failures": ["RECOVERY_NOT_EXECUTED"]}
    return {"verdict": "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": []}
