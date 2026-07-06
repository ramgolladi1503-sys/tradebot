from core.decision_engine import evaluate_candidate_decision

def _base_candidate(**overrides):
    base = {
        "trade_id": "T-DECIDE-1",
        "symbol": "NIFTY",
        "candidate_status": "near_executable",
        "candidate_class": "real",
        "execution_status": "scored",
        "execution_entry": 150.0,
        "execution_entry_status": "executable",
        "display_entry": 150.0,
        "display_entry_status": "displayable",
        "entry": 150.0,
        "entry_price": 150.0,
        "stop_loss": 120.0,
        "target": 210.0,
        "execution_allowed": True,
        "execution_ok": True,
        "eligible_for_execution": True,
        "tradable": True,
        "hard_blockers": [],
        "blockers": [],
        "quote_ok": True,
        "quote_age_sec": 0.5,
        "best_bid": 149.8,
        "best_ask": 150.2,
        "ltp": 150.0,
        "quote_completeness": "FULL",
    }
    base.update(overrides)
    return base

import sys
res = evaluate_candidate_decision(_base_candidate())
print(res)
