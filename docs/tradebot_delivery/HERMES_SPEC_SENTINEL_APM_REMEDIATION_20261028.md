# Hermes Architecture Specification: Sentinel APM & Live Stream Hardening

**Document ID:** `HERMES-SPEC-SENTINEL-APM-20261028`  
**Pipeline Stage:** Stage 1 (Hermes Architecture & Contracts)  
**Target Subsystems:**
1. `core/active_position_manager.py` (Finite State Machine, Trailing Stop, Tranche Accounting)
2. `core/sentinel_live_stream_advisor.py` (Mode 2 ORB Regime Gating, Anti-Churn Cooldown Admission)
3. `core/analytics/multi_session_aggregator.py` & `core/analytics/quant_metrics_engine.py` (Tranche Accounting Integration)

**Safety Invariants:**
```text
read_only = True
is_order_action = False
broker_api_called = False
allowed_for_live_execution = False
append = False
```

---

## 1. Architectural Mandates & Invariant Specifications

### Mandate 1: Monotonic Breakeven Floor & Giveback Clamp
- **Problem:** When an option makes a strong run (e.g. SENSEX +85 pts, NIFTY +24 pts) and achieves Target 1 (`half_booked == True`), the trailing stop formula `opt_cushion = max(25.0, 0.20 * peak)` expands aggressively. At peak = 634, cushion is 126.8 pts, placing the trailing SL at 507.2 (41.8 pts below entry). Booked winners are transformed into tail losses.
- **Contract Invariant 1.1 (Monotonic Floor):**
  Once `half_booked == True`, the option trailing stop MUST satisfy:
  $$\text{runner\_trailing\_sl} \ge \text{opt\_entry\_ltp} + \text{friction\_buffer}$$
  where `friction_buffer` is $2.0\text{ pts}$ for NIFTY, $3.0\text{ pts}$ for BANKNIFTY, and $5.0\text{ pts}$ for SENSEX.
- **Contract Invariant 1.2 (Bounded Progressive Giveback Clamp):**
  The trailing cushion $\Delta_{\text{cushion}}$ must be clamped such that the runner preserves at least $65\%$ of maximum peak excursion:
  $$\Delta_{\text{cushion}} = \min(1.5 \times \text{eff\_atr}, 0.35 \times (\text{opt\_peak\_hwm} - \text{opt\_entry\_ltp}))$$
  Under this invariant, an 85 pt excursion in SENSEX retains at least $+55.25\text{ pts}$ of gain.

---

### Mandate 2: Finite State Machine Expansion (`STATE_COOL_OFF`)
- **Problem:** Liquidating a trade moves the APM to `STATE_LIQUIDATED`. In `sentinel_live_stream_advisor.py`, `STATE_LIQUIDATED` is treated as an immediately eligible state for entry. Because price remains past the static Opening Range breakout level, the engine re-enters the exact same direction within 2 seconds into trend exhaustion.
- **Contract Invariant 2.1 (FSM Transitions):**
  Add `STATE_COOL_OFF` to `VALID_TRANSITIONS`:
  ```text
  STATE_EXIT_PENDING -> STATE_COOL_OFF -> STATE_STANDBY
  ```
- **Contract Invariant 2.2 (Dual Clearance Gate):**
  APM remains in `STATE_COOL_OFF` until BOTH of the following conditions are met:
  1. **Temporal Clearance:** Elapsed time $\Delta t \ge t_{\text{cooldown}}$, where:
     $$t_{\text{cooldown}} = \max(180\text{s}, \min(900\text{s}, 300\text{s} \times \frac{\text{ATR}_{1\text{m}}}{\text{ATR}_{15\text{m}}}))$$
     (Baseline 3 minutes, expanding in high-volatility chop).
  2. **Structural Extreme Clearance:** The underlying spot must either print a higher high (for CE) / lower low (for PE) relative to the liquidation price, OR return inside the Opening Range boundary.
- **Contract Invariant 2.3 (Admission Veto):**
  `sentinel_live_stream_advisor.py` must reject ANY signal where `idx_apm.state in {STATE_COOL_OFF, STATE_IN_FLIGHT, STATE_TRAIL_LOCK, STATE_EXIT_PENDING}`.

---

### Mandate 3: Discrete Multi-Tranche Ledger Schema & Accounting Realism
- **Problem:** When `half_booked == True`, 50% lot is banked at Target 1, but WAL `opt_pnl_pts` computes $LTP_{\text{exit}} - LTP_{\text{entry}}$ across the entire lot on runner liquidation, completely erasing banked Target 1 cash flow.
- **Contract Invariant 3.1 (Tranche Data Fields in `PositionPayload`):**
  ```python
  opt_half_booked_ltp: Optional[float] = None     # Fill price of Tranche 1 (50% lot)
  opt_half_booked_time: Optional[str] = None      # Timestamp of Tranche 1 fill
  tranche_1_pnl_pts: Optional[float] = None        # opt_half_booked_ltp - opt_entry_ltp
  runner_exit_ltp: Optional[float] = None          # Exit price of Tranche 2 (runner)
  runner_pnl_pts: Optional[float] = None           # runner_exit_ltp - opt_entry_ltp
  blended_opt_pnl_pts: Optional[float] = None      # 0.5 * tranche_1_pnl_pts + 0.5 * runner_pnl_pts
  ```
- **Contract Invariant 3.2 (WAL Backward Compatibility):**
  To maintain backward compatibility with external WAL consumers:
  - If `half_booked == False`, `opt_pnl_pts = opt_exit_ltp - opt_entry_ltp`.
  - If `half_booked == True`, `opt_pnl_pts = blended_opt_pnl_pts`.
- **Contract Invariant 3.3 (Quant Analytics Ingestion):**
  `NormalizedTrade` in `multi_session_aggregator.py` ingests `tranche_1_pnl_pts`, `runner_pnl_pts`, and `blended_opt_pnl_pts`. When present, `QuantMetricsEngine` computes gross and net PnL from the blended points.

---

### Mandate 4: Mode 2 ORB Regime Gating & De-Mocking
- **Problem:** In `sentinel_live_stream_advisor.py`, Mode 2 ORB triggers directional trades blindly without checking `RegimeRouter`, and lines 554 and 657 hardcode `writer_conviction = 0.75` and `session_gear = "GEAR_2_TREND"`.
- **Contract Invariant 4.1 (Regime Admission Gate):**
  Mode 2 ORB MUST evaluate `regime_router`:
  ```python
  router = self.regime_routers.get(index_name)
  if router:
      post = router.get_posterior()
      if not post.permissions.get("ORB", False) or post.dominant_regime == "ROTATIONAL_CHOP":
          # Suppress breakout during chop
          return
  ```
- **Contract Invariant 4.2 (Orderbook Conviction Derivation):**
  Derive `writer_conviction` dynamically from L2 book depth imbalance rather than hardcoding `0.75`:
  $$\text{depth\_imbalance} = \frac{\sum \text{Bids} - \sum \text{Asks}}{\sum \text{Bids} + \sum \text{Asks}}$$
  $$\text{writer\_conviction} = \text{clamp}(0.5 + 0.5 \times \text{depth\_imbalance}, 0.20, 0.95)$$

---

## 2. Verification Gate Criteria
1. **Gate A:** Dedicated unit test proving that a position running $+85\text{ pts}$ into Target 1 cannot exit below `opt_entry_ltp + friction_buffer`.
2. **Gate B:** Dedicated unit test proving that after liquidation, `STATE_COOL_OFF` is entered and blocks any new entry for the duration of the cool-off window.
3. **Gate C:** Dedicated unit test proving that multi-tranche PnL correctly records $50\%$ at Target 1 and $50\%$ at runner exit, calculating true blended PnL.
4. **Gate D:** Regression test passing all existing APM and analytics tests.
