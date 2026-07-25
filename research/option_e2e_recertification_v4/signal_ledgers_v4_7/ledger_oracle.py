from __future__ import annotations


def certify_ledger(records):
    return {"verdict": "SIGNAL_LEDGER_NOT_CERTIFIED" if not records else "SIGNAL_LEDGER_CERTIFIED", "records": records, "failures": [] if records else ["EMPTY_SIGNAL_LEDGER"]}
