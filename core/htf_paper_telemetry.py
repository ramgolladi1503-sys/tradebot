import json
import os
from datetime import datetime
from pathlib import Path
from core.runtime_execution_truth import execution_truth_decision

CANDIDATES_LOG = Path("runtime/paper/htf_opening_drive_candidates.jsonl")
EXITS_LOG = Path("runtime/paper/htf_opening_drive_exits.jsonl")

def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

def _get_val(obj, key, default=""):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def log_htf_opening_drive_paper_candidate(trade: dict, market_data: dict) -> None:
    """
    Paper telemetry validation hook.
    Logs actual option quote metrics (bid/ask/spread/staleness) for HTF_OPENING_DRIVE_CONT candidates.
    This does not log if live execution is attempted, this is strictly a paper telemetry artifact.
    """
    if not trade:
        return

    fam = _get_val(trade, "family", getattr(trade, "strategy_family", ""))
    strat = _get_val(trade, "strategy", getattr(trade, "strategy_name", getattr(trade, "strategy_id", fam)))
    print(f"TELEMETRY SEES: strat={strat}, fam={fam}, trade={trade}")
    
    if "OPENING_DRIVE_CONT" not in str(strat) and "OPENING_DRIVE_CONT" not in str(fam):
        return

    # Evaluate truth using the same method opportunity_engine uses to evaluate candidates
    from core.opportunity_engine import _execution_truth
    truth = _execution_truth(trade)
    
    # Extract option quotes
    chain = market_data.get("option_chain", [])
    strike = _get_val(trade, "strike")
    opt_type = _get_val(trade, "type", _get_val(trade, "option_type"))
    
    bid, ask, spread, quote_age = 0.0, 0.0, 0.0, 0.0
    for opt in chain:
        if opt.get("strike") == strike and opt.get("type") == opt_type:
            bid = opt.get("bid", 0.0)
            ask = opt.get("ask", 0.0)
            spread = ask - bid if ask and bid else 0.0
            quote_age = opt.get("quote_age_sec", 0.0)
            break
            
    is_fallback = truth.get("is_fallback", False) or bool(_get_val(trade, "is_fallback"))
    is_advisory = truth.get("is_advisory", False) or _get_val(trade, "status") == "ADVISORY_ONLY"
    
    record = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "cycle_id": market_data.get("run_id") or "unknown",
        "candidate_id": _get_val(trade, "candidate_id") or "unknown",
        "strategy": strat,
        "index_level_at_signal": market_data.get("ltp"),
        "selected_option_instrument": f"{_get_val(trade, 'symbol')}_{strike}_{opt_type}",
        "strike": strike,
        "expiry": _get_val(trade, "expiry"),
        "CE_PE_side": opt_type,
        "option_entry_LTP": _get_val(trade, "entry_price"),
        "bid": bid,
        "ask": ask,
        "spread": spread,
        "quote_age": quote_age,
        "target": _get_val(trade, "target"),
        "stop": _get_val(trade, "stop"),
        "time_stop": "15:15",
        "proxy_expected_pnl": _get_val(trade, "proxy_expected_pnl"),
        "actual_paper_entry_price": _get_val(trade, "entry_price", 0.0) if truth.get("truth_allows_execution", False) else 0.0,
        "is_fallback": is_fallback,
        "is_advisory": is_advisory,
        "is_stale": quote_age > getattr(market_data.get("cfg", object), "STALE_QUOTE_AGE_SEC", 5.0),
        "execution_ok": truth.get("truth_allows_execution", False)
    }
    
    _ensure_dir(CANDIDATES_LOG)
    with open(CANDIDATES_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")

def log_htf_opening_drive_paper_exit(exit_record: dict) -> None:
    if exit_record.get("strategy_family") != "OPENING_DRIVE_CONT":
        return
        
    record = {
        "candidate_id": exit_record.get("candidate_id"),
        "exit_timestamp": datetime.utcnow().isoformat() + "Z",
        "exit_reason": exit_record.get("terminal_status") or exit_record.get("exit_reason"),
        "exit_LTP": exit_record.get("exit_price"),
        "exit_bid": exit_record.get("metadata", {}).get("exit_bid"),
        "exit_ask": exit_record.get("metadata", {}).get("exit_ask"),
        "realized_paper_pnl": exit_record.get("slippage_adjusted_pnl"),
        "slippage_estimate": exit_record.get("slippage_cost"),
        "proxy_pnl_vs_actual_option_pnl": exit_record.get("gross_pnl"),
    }
    
    _ensure_dir(EXITS_LOG)
    with open(EXITS_LOG, "a") as f:
        f.write(json.dumps(record) + "\n")
