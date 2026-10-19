# Work Item: FEAT-STRUCTURAL-ALPHA-003
# Title: 4 Structural Non-Overfitted Profitability & Execution Modules
# Status: ARCHITECTURE_DRAFT / UNDER_REVIEW

## 1. Overview & Objective
Empirical analysis of execution logs across October sessions (specifically 2026-10-19) proved that while underlying directional calls (PE breakdown) were structurally correct (+100pt move), net performance suffered from:
1. Far OTM delta lag and poor gamma efficiency ($\Delta < 0.35$).
2. Aggressive spread crossing penalty (paying full Ask on entry and Bid on exit, causing ₹1,535 frictional fee/spread drag).
3. Entering during volatility exhaustion rather than post-compression expansion.
4. False breakouts occurring when single index diverged against broader market indices (NIFTY vs SENSEX vs BANKNIFTY).

This work item implements 4 invariant structural alpha gates to systematically resolve these issues without curve-fitting.

## 2. Structural Modules
### Module 1: ITM / High-Delta Strike Selection Engine (`ITMStrikeResolver`)
- **Invariant**: Target Delta $\Delta \in [0.65, 0.75]$ (ATM -1 strike for CE, ATM +1 strike for PE; 50-pt ITM on NIFTY, 100-200pt ITM on SENSEX).
- **Property**: High delta allows 1:1 spot tracking, dampens extrinsic theta decay, and ensures tight bid-ask spreads with deep market depth.

### Module 2: Passive Midpoint Execution Queue Model (`MidpointQueueModel`)
- **Invariant**: Evaluates simulated limit fills at the midpoint $\frac{P_{\text{bid}} + P_{\text{ask}}}{2}$ rather than crossing the entire spread.
- **Microstructure**: If spread $> 1.0$ pt, model posts passive limit at midpoint or top-queue join. If subsequent trades/ticks print through the midpoint, entry is credited at midpoint saving 1.5–3.0 pts per round trip.

### Module 3: Volatility Compression & NR4 Pre-Conditioning (`VolatilityCompressionGate`)
- **Invariant**: Trend setups require stored kinetic energy. Evaluates compression ratio $C_R = \frac{\text{ATR}_{15m}}{\text{ATR}_{60m}} \le 0.85$ or Narrow Range 4 (NR4) condition.
- **Fail-Closed Gate**: If the market has already expanded $> 2.5 \times \text{ATR}_{60m}$ without a base, setup is classified as `EXHAUSTED_EXPANSION` and entry is suppressed.

### Module 4: Cross-Index Macro Confirmation Gate (`CrossIndexMacroGate`)
- **Invariant**: Directional setups on NIFTY/SENSEX must be confirmed by concurrent directional displacement on the other index within a 3-minute lookback ($\Delta t \le 180s$).
- **Veto Condition**: If NIFTY triggers a breakdown but SENSEX is printing above its VWAP/Opening Range High, the trade is marked `DIVERGENCE_VETO` and suppressed.

## 3. Strict Safety Invariants
- `read_only = True`
- `is_order_action = False`
- `broker_api_called = False`
- `allowed_for_live_execution = False`
- `status = NO_CERTIFIED_EDGE`
