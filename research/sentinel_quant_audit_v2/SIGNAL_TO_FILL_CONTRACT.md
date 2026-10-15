# SENTINEL SIGNAL-TO-FILL CONTRACT SPECIFICATION

**Contract Status:** PROPOSED CHALLENGER SPECIFICATION  
**Scope:** Buy CE / Buy PE Intraday Options  
**Advisory Interface:** Broker-Free, Event-Driven, Manual Approval Invariant

---

## 1. Scope & Execution Principles

1. **Pure Advisory Role:**
   - The Sentinel Engine produces prospective trade advisories only (`read_only=true`, `is_order_action=false`, `broker_api_called=false`).
   - Under no circumstances does the engine place broker orders or route live capital.
2. **Buy-Only Directionality:**
   - Only `BUY CE` (bullish expansion) and `BUY PE` (bearish expansion) orders are permitted.
   - Naked option writing, straddles, and spreads are prohibited.

---

## 2. Invariant Requirements for Signal Generation

A directional breakout advisory is emitted **if and only if** all the following causal gates evaluate to `PASS`:

1. **Causal Time Gate ($T \ge 09:30:00$ IST):**
   - No signals may be emitted during the 15-minute Opening Range establishment phase $[09:15, 09:30)$.
2. **Opening Range Boundary Penetration:**
   - `BUY CE`: Bar Close $> OR_{high} + \Delta_{buf}$
   - `BUY PE`: Bar Close $< OR_{low} - \Delta_{buf}$
3. **Candle Body Conviction (Wick Filter):**
   - The candle body must constitute a dominant fraction of the total range:
     $$\frac{|\text{Close} - \text{Open}|}{\text{High} - \text{Low}} \ge 0.60 \quad \text{and} \quad |\text{Close} - \text{Open}| \ge \text{wick\_min}$$
4. **Kaufman Efficiency Ratio (KER Filter):**
   - Directional persistence across the lookback window must exceed noise threshold:
     $$KER = \frac{|P_t - P_{t-n}|}{\sum_{i=1}^n |P_i - P_{i-1}|} \ge 0.35$$
5. **Brownian Energy Gate (Diffusion Capacity):**
   - Accumulated session variance must not exceed theoretical Brownian dispersion limits for the time of day:
     $$\text{Residual Energy} > 0.15 \times \sigma_{session}$$
6. **Session Chop Loss Gate (New Challenger Invariant):**
   - If the current session has incurred $\ge 2$ consecutive stop-out losses, **all further entries for the session are permanently halted** (Chop Circuit Breaker).

---

## 3. Fill Model & Price Discovery Rules (Challenger Simulation)

When evaluating prospective paper executions, the simulator must adhere to the following conservative fill conventions:

1. **Option Strike Selection:**
   - Strike must resolve to 1-strike In-The-Money (ITM) using the exact current weekly contract master.
   - NIFTY: Rounded to nearest 50 pt boundary $\pm 50$ pts.
   - SENSEX: Rounded to nearest 100 pt boundary $\pm 100$ pts.
2. **Pessimistic Bid-Ask Crossing:**
   - Long Entry: Filled at `Ask` price (or `LTP + 1 tick` if depth is unquoted).
   - Long Exit: Filled at `Bid` price (or `LTP - 1 tick` if depth is unquoted).
3. **Intrabar Boundary Collision Invariant:**
   - If in any 1-minute candle both the Stop Loss and Target are reached ($\text{Low} \le SL$ and $\text{High} \ge TP$), the state machine **must resolve as `STOP_LOSS_HIT`**. Target fills are never awarded on ambiguous collision candles.
4. **Execution Latency Budget:**
   - Simulated fill timestamp must be $T_{bar\_close} + 250 \text{ ms}$ to account for signal processing, token lookup, and WebSocket round-trip.

---

## 4. Statutory Drag & Net Expectancy Formula

Simulated net performance must report three distinct tracks:
- **Track 0:** Spot Index Movement ($\Delta S = S_{exit} - S_{entry}$)
- **Track 1:** Gross Option Movement ($\Delta C = C_{exit} - C_{entry}$)
- **Track 2:** Net Realized Rupee P&L:
  $$\text{Net PnL} = [(\Delta C - 2 \times \text{Tick}) \times \text{LotSize}] - \text{Statutory Friction}$$
  Where Statutory Friction includes Brokerage (Rs 40), STT (0.125% sell turnover), Exchange Turnover Fees (0.05%), GST (18%), and Stamp Duty (0.003%).
