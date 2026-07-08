import pytest
import pandas as pd
from scripts.audit_regime_strategy_switching import align_and_compare, evaluate_verdict, apply_negative_control

def test_audit_no_hardcoded_match_rate():
    # Providing zero aligned rows should result in 0% match rate, not 100%
    ref_records = []
    tb_records = []
    t_ref, t_tb, aligned, m_ref, m_tb, rm, rmm, rmr, sm, smm, smr, mismatches = align_and_compare(ref_records, tb_records)
    assert rmr == 0.0

def test_negative_control_swap_labels():
    ref_records = [{"market_timestamp": "2026-07-06 09:15:00", "reference_regime": "TREND_UP", "reference_strategy_family": "Trend"}]
    tb_records = [{"market_timestamp": "2026-07-06 09:15:00", "tradebot_regime": "TREND_UP", "selected_strategy": "Trend"}]
    
    df = pd.DataFrame(ref_records)
    
    # Original aligned match rate
    _, _, aligned, _, _, rm, _, rmr, _, _, _, _ = align_and_compare(ref_records, tb_records)
    assert aligned == 1
    assert rmr == 1.0
    
    # Apply negative control
    df, modified_ref = apply_negative_control(df, ref_records, "swap_reference_labels")
    assert modified_ref[0]["reference_regime"] == "TREND_DOWN"
    
    # New match rate
    _, _, aligned, _, _, rm, _, rmr, _, _, _, _ = align_and_compare(modified_ref, tb_records)
    assert rmr == 0.0

def test_shifted_timestamps_time_window_mismatch():
    ref_records = [{"market_timestamp": "2026-07-06 09:15:00", "reference_regime": "TREND_UP", "reference_strategy_family": "Trend"}]
    tb_records = [{"market_timestamp": "2026-07-06 10:15:00", "tradebot_regime": "TREND_UP", "selected_strategy": "Trend"}]
    
    t_ref, t_tb, aligned, m_ref, m_tb, rm, rmm, rmr, sm, smm, smr, mismatches = align_and_compare(ref_records, tb_records)
    assert aligned == 0
    verdict = evaluate_verdict(aligned, None, 1, "none", rmr)
    assert verdict == "TIME_WINDOW_MISMATCH"

def test_missing_ohlc_columns():
    verdict = evaluate_verdict(0, "INSUFFICIENT_SCHEMA", 0, "none", 0.0)
    assert verdict == "INSUFFICIENT_SCHEMA"
