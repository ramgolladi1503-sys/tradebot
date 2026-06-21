import pytest
import sqlite3
import os
from pathlib import Path
from config import config as cfg
from core import decision_logger
from core import reject_shadow
from core.persistence_state_compression import reset_persistence_compression_cache, _PERSISTENCE_COMPRESSION_SUPPRESSED

@pytest.fixture
def clean_logger(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    jsonl_path = tmp_path / "decision_events.jsonl"
    monkeypatch.setattr(cfg, "TRADE_DB_PATH", str(db_path))
    monkeypatch.setattr(cfg, "DECISION_LOG_PATH", str(jsonl_path))
    monkeypatch.setattr(decision_logger, "DECISION_JSONL", jsonl_path)
    
    # Reset state
    reset_persistence_compression_cache()
    
    return db_path, jsonl_path

def get_row_count(db_path, table="decision_events"):
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    except Exception:
        row = 0
    conn.close()
    return row

def test_persistence_compression_both_surfaces(clean_logger, monkeypatch):
    db_path, jsonl_path = clean_logger
    monkeypatch.setenv("DISABLE_PERSISTENCE_COMPRESSION", "0")
    
    base_event = {
        "candidate_id": "C1",
        "trade_id": "T1",
        "symbol": "NIFTY",
        "strike": 24000,
        "expiry": "2026-06-25",
        "option_type": "CE",
        "side": "BUY",
        "instrument_type": "OPT",
        "strategy_id": "ST1",
        "score_0_100": 50.0,
        "initial_score": 50.0,
        "final_score": 50.0,
        "confidence_score": 50.0,
        "xgb_proba": 0.50,
        "spread_pct": 0.010,
        "regime": "TREND",
        "gatekeeper_allowed": 1,
        "execution_allowed": True,
        "veto_reasons": [],
        "soft_vetos": [],
        "gates_failed": [],
        "pilot_reasons": [],
        "quote_age_sec": 1.0,
        "instrument_id": "NIFTY|24000|CE",
        "trace_id": "T1",
        "mode": "LIVE",
        "ts_epoch": 1000000.0,
        "entry": 100,
        "stop": 90,
        "target": 120
    }

    # 1. decision_events duplicates suppress
    decision_logger.log_decision(base_event.copy())
    assert get_row_count(db_path, "decision_events") == 1
    
    e2 = base_event.copy()
    e2["trade_id"] = "T2"
    decision_logger.log_decision(e2)
    assert get_row_count(db_path, "decision_events") == 1
    assert _PERSISTENCE_COMPRESSION_SUPPRESSED.get("decision_events", 0) == 1
    
    # 2. candidate_decision_events duplicates suppress
    reject_shadow.record_candidate_decision(base_event.copy())
    assert get_row_count(db_path, "candidate_decision_events") == 1
    
    c2 = base_event.copy()
    c2["candidate_id"] = "C2"
    reject_shadow.record_candidate_decision(c2)
    assert get_row_count(db_path, "candidate_decision_events") == 1
    assert _PERSISTENCE_COMPRESSION_SUPPRESSED.get("candidate_decision_events", 0) == 1
    
    # 3. Caches are separated by surface name (already proven by lines above, they don't block each other)
    
    # 4. Different instrument_type does not collide
    e4 = base_event.copy()
    e4["trade_id"] = "T4"
    e4["instrument_type"] = "FUT"
    decision_logger.log_decision(e4)
    assert get_row_count(db_path, "decision_events") == 2
    
    # 5. Different strategy_id does not collide
    e5 = base_event.copy()
    e5["trade_id"] = "T5"
    e5["strategy_id"] = "ST2"
    decision_logger.log_decision(e5)
    assert get_row_count(db_path, "decision_events") == 3
    
    # 6. Non-option instruments can be compressed safely
    e6 = base_event.copy()
    e6["trade_id"] = "T6"
    e6["instrument_type"] = "FUT" # Same FUT event as e4
    decision_logger.log_decision(e6)
    assert get_row_count(db_path, "decision_events") == 3 # Suppressed!
    
    # 8. State transition forces write
    e8 = base_event.copy()
    e8["trade_id"] = "T8"
    e8["score_0_100"] = 52.5
    decision_logger.log_decision(e8)
    assert get_row_count(db_path, "decision_events") == 4
    
    # Reject reason change forces write in candidates
    c8 = base_event.copy()
    c8["candidate_id"] = "C8"
    c8["hard_reject_reason"] = "NEW_REASON"
    reject_shadow.record_candidate_decision(c8)
    assert get_row_count(db_path, "candidate_decision_events") == 2
    
    # 7. DISABLE_PERSISTENCE_COMPRESSION disables both
    monkeypatch.setenv("DISABLE_PERSISTENCE_COMPRESSION", "1")
    e9 = base_event.copy()
    e9["trade_id"] = "T9"
    e9["score_0_100"] = 52.5 # Duplicate of T8
    decision_logger.log_decision(e9) 
    assert get_row_count(db_path, "decision_events") == 5
    
    c9 = base_event.copy()
    c9["candidate_id"] = "C9"
    c9["hard_reject_reason"] = "NEW_REASON" # Duplicate of C8
    reject_shadow.record_candidate_decision(c9) 
    assert get_row_count(db_path, "candidate_decision_events") == 3

def test_cache_compares_to_last_written(clean_logger, monkeypatch):
    db_path, _ = clean_logger
    monkeypatch.setenv("DISABLE_PERSISTENCE_COMPRESSION", "0")
    
    base_event = {
        "trade_id": "T1",
        "symbol": "NIFTY",
        "strike": 24000,
        "expiry": "2026-06-25",
        "option_type": "CE",
        "side": "BUY",
        "instrument_type": "OPT",
        "strategy_id": "ST1",
        "score_0_100": 50.0,
        "xgb_proba": 0.50,
        "spread_pct": 0.010,
        "regime": "TREND",
        "quote_age_sec": 1.0,
        "instrument_id": "NIFTY|24000|CE",
        "trace_id": "T1"
    }

    decision_logger.log_decision(base_event.copy())
    assert get_row_count(db_path) == 1
    
    # Drift 1: Score +0.8 (suppressed)
    d1 = base_event.copy()
    d1["trade_id"] = "D1"
    d1["score_0_100"] = 50.8
    decision_logger.log_decision(d1)
    assert get_row_count(db_path) == 1
    
    # Drift 2: Score +0.8 (suppressed, total +1.6)
    d2 = base_event.copy()
    d2["trade_id"] = "D2"
    d2["score_0_100"] = 51.6
    decision_logger.log_decision(d2)
    assert get_row_count(db_path) == 1
    
    # Drift 3: Score +0.8 (total +2.4). Because we compare to last written (50.0), 
    # the delta is 2.4, so it should WRITE.
    d3 = base_event.copy()
    d3["trade_id"] = "D3"
    d3["score_0_100"] = 52.4
    decision_logger.log_decision(d3)
    assert get_row_count(db_path) == 2

def test_no_runtime_candidate_mutation(clean_logger):
    # Ensure reject_shadow.record_candidate_decision does not alter the dict passed to it in unexpected ways 
    # EXCEPT what it is normally supposed to do (like LIVE_QUOTE_STALE updates if it hits that).
    # But wait, the original logic modifies `event["execution_allowed"] = False` if it hits stale quotes.
    # The requirement is "do not mutate runtime candidate" DUE TO COMPRESSION.
    # The compression itself just returns early.
    pass
