# HTF OPENING_DRIVE_CONT Paper Validation Plan

## Goal
Validate the edge of `OPENING_DRIVE_CONT` using actual live option bid/ask quotes without exposing the system to live execution risk. The research replay demonstrated proxy-based edge, but real-world option liquidity and spread costs must be measured before promoting this strategy to live.

## Constraints
1. **No Live Orders:** The system is explicitly configured to log `OPENING_DRIVE_CONT` purely as a paper intent. It must NEVER execute a live broker order.
2. **Strategy Isolation:** ONLY `OPENING_DRIVE_CONT` is eligible for paper validation. All other HTF strategies (`15M_TREND_CONT`, `15M_VWAP_PULLBACK`, `FAILED_BREAKOUT_REVERSAL`, `PDH_PDL_HOLD`) remain non-executable/feature-only.
3. **Gate Rigidity:** Fallback, advisory, stale-quote, and recovered candidates are unconditionally non-executable. The safety gates remain fully enforced.

## Telemetry Capture
To capture option friction cleanly, two new isolated logs have been added:
* **Candidates:** `runtime/paper/htf_opening_drive_candidates.jsonl`
* **Exits:** `runtime/paper/htf_opening_drive_exits.jsonl`

These files contain the precise option snapshot (LTP, bid, ask, spread, quote age) at the time of entry and exit. 

## Success Criteria
Before any discussion of live promotion can occur, the strategy must:
1. Capture 30–50 valid paper trades.
2. Prove that the real option spread/slippage aligns with the proxy-cost estimates used in the research replay.
3. Show positive `slippage_adjusted_pnl` over the sample size.

To monitor progress, run:
```bash
python scripts/summarize_htf_opening_drive_paper.py
```
