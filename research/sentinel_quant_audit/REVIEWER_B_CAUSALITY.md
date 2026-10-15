# Reviewer B — Market Data, Causality & Replay Forensics Report

## 1. Timestamp & Clock Auditing
- **1-Minute Bar Timestamping**:
  - Live feed bars are timestamped at the completed bar close (e.g. `10:01:00` represents the completed interval `10:00:00 -> 10:01:00`).
  - No intrabar lookahead: The advisor polls `get_historical_candle_data1()` and executes strictly *after* the bar boundary is confirmed.
- **Option Quote Causality**:
  - `resolve_real_option_quote` passes `decision_cutoff_epoch = bar_close_cutoff_epoch`.
  - Quotes with `source_capture_ts > bar_close_cutoff_epoch` are strictly rejected.
  - Verified in live log: On Oct 15, all evaluated option quotes had timestamps strictly prior to the evaluated bar close.

## 2. Intrabar SL/TP First-Passage Ambiguity
- **The Issue**: In 1-minute bar backtests, if both High $\ge$ Target and Low $\le$ Stop Loss occur in the same bar, which happened first?
- **Sentinel Implementation**:
  - In `core/sentinel_active_position_manager.py`:
    ```python
    if hit_sl and hit_tp:
        # Conservative fail-closed resolution
        exit_price = current_sl
        exit_reason = "STOP_LOSS_HIT"
    ```
  - **Verdict**: Causally sound. The code assumes the pessimistic outcome (SL wins over TP), preventing optimistic fill illusions.

## 3. Tick Latency & Feed Dropout Impact
- On Oct 15 at 12:17:30, a transient network error occurred.
- The engine did not hallucinate fills during the outage; it skipped evaluation and resumed cleanly at 12:18:00 without dangling state corruption.
