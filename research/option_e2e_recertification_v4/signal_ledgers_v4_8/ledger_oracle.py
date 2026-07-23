from __future__ import annotations


def certify_ledger(records):
    if not records:
        return {"verdict": "NO_SIGNALS_UNDER_FROZEN_CONTRACT", "records": [], "failures": ["EMPTY_SIGNAL_LEDGER"]}
    return {"verdict": "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": []}
