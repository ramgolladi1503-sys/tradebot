# Work Item: FEAT-GIVEBACK-CLAMP-PULLBACK-005
# Title: Dynamic Peak Giveback Clamp & Trend Pullback Re-Entry State Machine
# Status: ARCHITECTURE_DRAFT / UNDER_REVIEW

## 1. Overview & Objective
Empirical analysis of intra-trade excursion logs reveals that multiple trades achieve strong positive unrealized gains (+12% to +30% option premium / +10 to +18 spot points) before stalling and retracing all the way back to initial Stop Loss (-20% option loss or -1.0 ATR spot loss). Furthermore, when stopped out at breakeven during natural market breathing, strong trend days frequently resume their primary trajectory without the engine, leaving significant alpha on the table.

This work item implements two institutional-grade execution risk controls:
1. **Dynamic Peak Giveback Clamp (`PeakGivebackClamp`)**:
   - **Tier 1 (Friction & Breakeven Lock)**: When option gain reaches $\ge +12\%$ of entry premium, spot SL snaps to Entry $+ 1.0\text{ pt}$ (or option SL to entry $+ 1.5\text{ pts}$ friction buffer).
   - **Tier 2 (Peak Profit Floor Clamp)**: When option gain reaches $\ge +25\%$, the engine establishes a guaranteed positive profit floor $\ge +10\%$ and limits peak giveback to at most $35\%$ of peak excursion (e.g. if option reached $+30\%$, it exits if it retreats below $+19.5\%$, locking in green profit).
2. **Trend Pullback Re-Entry State Machine (`STATE_PULLBACK_WAIT`)**:
   - When a trade exits via `TRAILING_STOP_HIT` or `PEAK_GIVEBACK_CLAMP_EXIT`, if and only if **Gear 2 Trend** (`session_gear == "GEAR_2_TREND"`) and **Multi-Index Alignment** remain fully active, transition the APM to `STATE_PULLBACK_WAIT`.
   - Allows strictly **at most 1 re-entry per setup** (`max_reentries_per_setup = 1`).
   - Re-entry triggers when price pulls back to test EMA-9 / VWAP and prints a confirmation bounce on Bar $T$, executing at Bar $T+1$ Open.
   - Forbids all re-entries in **Gear 1 Chop** (`session_gear == "GEAR_1_RANGE"`), preventing fee and bid-ask spread churn.

## 2. Invariant Specifications & State Transitions
- `VALID_TRANSITIONS` updated:
  - `STATE_IN_FLIGHT`: `{STATE_TRAIL_LOCK, STATE_EXIT_PENDING, STATE_PULLBACK_WAIT}`
  - `STATE_TRAIL_LOCK`: `{STATE_EXIT_PENDING, STATE_PULLBACK_WAIT}`
  - `STATE_PULLBACK_WAIT`: `{STATE_ARMED, STATE_LIQUIDATED, STATE_STANDBY}`
- `reentry_count`: Monotonically capped at 1.
- `peak_giveback_pct`: Capped at $0.35$ (35% giveback of peak option gain).

## 3. Strict Safety Invariants
- `read_only = True`
- `is_order_action = False`
- `broker_api_called = False`
- `allowed_for_live_execution = False`
- `status = NO_CERTIFIED_EDGE`
- `future_bar_leakage = False` (Bar $T+1$ Open execution).
