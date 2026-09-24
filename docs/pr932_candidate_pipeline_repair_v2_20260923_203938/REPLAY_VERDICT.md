# Replay Verdict: Real 2026-09-23 Market Data

- **Capture Date**: 2026-09-23
- **Index Data**: 1,500 bars (`indices_1m_20260923.parquet`)
- **Tick Data**: 7,912,685 ticks (`upstox_full_ticks_20260923_stitched.parquet`)
- **Result**:
  - CAS Morning Reversal triggered at 10:00:00 IST (+12.05 bps return).
  - Direction: SELL / PE Option Advisory.
  - Successfully entered candidate pool and executable pool.
  - Successfully evaluated by Shadow RiskEngine (`RiskEngine.evaluate_trade`).
  - Emitted canonical `trade_truth_stream.jsonl`.
  - Verdict: **VERIFIED WORKING CLEANLY ON REAL DATA**.
