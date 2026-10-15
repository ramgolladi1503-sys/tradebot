# SENTINEL CHALLENGER INDEPENDENT FALSIFICATION & ADVERSARIAL AUDIT REPORT

**Mission:** Independently validate or disprove the reported +₹2,417.83 chop-breaker result.  
**Branch:** `research/sentinel-quant-audit-20261015`  
**PR:** #985  
**Protected Baselines:** PR #968 (`e6d0ae46643ba21767e13e0c40fa8389e51d1acb`) and PR #980 (`c87688055c3df2d77a4220eb1c0c4d763db9c5c2`) — **100% frozen and untouched**.

---

## 1. Adversarial Falsification of the +₹2,417.83 Chop-Breaker Result

### The Core Scientific Question:
*Does a 2-consecutive-loss circuit breaker identify a genuine regime property of market chop, or does it merely curve-fit to October 14 by happening to cut off the single largest loss of the day (-40.75 opt pts in Trade #5)?*

### Parametric Sensitivity Sweep (Limits $L \in \{1, 2, 3, 4, \infty\}$):

To answer this without cherry-picking, the audit executed an unconstrained parameter sweep across all 26 audited trades using identical causality rules, true contract lot sizes (NIFTY 65 qty, SENSEX 20 qty), and October 2024 revised SEBI statutory STT rates (0.10% sell turnover):

| Parameterization | Executed Trades | Blocked Trades | Win / Loss | Net Rupee P&L | Drawdown vs Baseline | Scientific Interpretation |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Limit = 1** (Halt on 1st loss) | 17 | 9 | 15 / 2 | **+Rs 5,488.34** | +Rs 5,594.96 | Extreme regime truncation. Halts after Oct 14 Trade #3 (-0.85 pts), completely avoiding both Trade #4 (-34.6 pts) and Trade #5 (-40.75 pts). High risk of false halting during normal pullbacks. |
| **Limit = 2** (Proposed Challenger) | 21 | 5 | 16 / 5 | **+Rs 2,458.67** | **+Rs 2,565.29** | Halts after Oct 14 Trade #4 (-34.6 pts). Cuts off Trade #5 (-40.75 pts) and three subsequent whipsaw losses. |
| **Limit = 3** (Halt on 3rd loss) | 22 | 4 | 16 / 6 | **-Rs 265.76** | -Rs 159.14 | Incurs Trade #5 (-40.75 pts). Net P&L turns negative immediately. |
| **Limit = 4** (Halt on 4th loss) | 23 | 3 | 16 / 7 | **-Rs 561.60** | -Rs 454.98 | Deep in net loss territory. |
| **No-Breaker (Baseline Control)** | 26 | 0 | 18 / 8 | **-Rs 106.62** | Baseline | Full churn across all 9 Oct 14 chop entries. |

### Quant Mechanism Verdict (Reviewer A & E):
**The positive ₹2,458.67 P&L at $L=2$ is highly sensitive to the exact trade sequence of October 14.**
- Specifically, October 14 happened to cluster two catastrophic option losses back-to-back: Trade #4 (-34.60 pts) and Trade #5 (-40.75 pts).
- Because Trade #3 was a small loss (-0.85 pts), a limit of $L=2$ absorbed Trade #4 as the 2nd loss and tripped *just in time* to avoid Trade #5.
- If Trade #5 had occurred earlier, or if Trade #3 had been a breakeven exit, $L=2$ would have absorbed Trade #5 and finished negative (-Rs 265.76).
- **Conclusion:** While session-level chop halting is a sound risk management heuristic, **the magnitude of the ₹2,458 P&L gain is an artifact of sample sequence clustering on a single day.** It cannot be certified as stable forward alpha.

---

## 2. Event-Time Causality & Fill Verification (Reviewer B & C)

### Causality Audit:
1. **Event-Time Ordering:**
   - In live replay, Trade #3 exited at `10:20:00` (Loss #1).
   - Trade #4 entered at `11:35:00` (75 minutes later) and exited at `11:57:49` (Loss #2).
   - Trade #5 was proposed at `13:39:00` (101 minutes later).
   - At `13:39:00`, the circuit breaker had access to both completed prior losses. The decision to halt at `13:39:00` is **100% causal and strictly lookahead-free**.
2. **True Bid/Ask vs Simulated LTP Fills:**
   - All 26 trades were audited against actual capture-time market depth in the WAL.
   - For all NIFTY trades, entry Ask was between $+0.20$ and $+0.45$ pts above LTP.
   - For SENSEX trades, entry Ask was between $+0.55$ and $+0.70$ pts above LTP.
   - Replacing simulated fills with true entry Asks slightly increases friction but does not alter trade directionality or loss classification.
   - `TRADE_1513_PE` (entered at 15:13 with no exit) is formally classified as `NOT_EVALUABLE` rather than assigned zero profit.

---

## 3. Dissecting the Three Oct 15 Divergent Trades (`TRADE_1006_CE`, `TRADE_1033_CE`, `TRADE_1045_CE`)

The user specifically mandated investigating why these three trades produced positive spot movement but negative option premium:

### Competing Explanations Evaluated:
1. **Hypothesis 1: Intraday Volatility (IV) Crush / Theta Decay**
   - *Forensic Test:* `TRADE_1006_CE` was held for only **2 minutes** (10:06 to 10:08). Theta decay on a 2-minute hold is $< 0.05$ pts. IV crush over 2 minutes was $< 0.15$ vol points.
   - *Verdict:* **REFUTED for Trade 1006.** Theta and IV crush cannot explain a -0.50 pt option loss in 120 seconds.
2. **Hypothesis 2: Premature Trailing Stop Ratchet & Spread Crossing**
   - *Forensic Test:* In `TRADE_1006_CE`, spot moved up by only **+1.00 pt** ($22879.8 \to 22880.8$). The APM trailed the stop to spot breakeven.
   - In an ITM option with $\Delta = 0.55$, a 1.0 pt spot move expands the option by only $+0.55$ pts.
   - The capture-time bid-ask spread was **0.40 pts** (Bid 149.95 / Ask 150.35).
   - When spot stalled and pulled back by 1 point, the exit order crossed the spread into the Bid at 149.45.
   - *Verdict:* **CONFIRMED PRIMARY DRIVER.** The trailing stop ratcheted prematurely on an excursion that was smaller than the bid-ask spread.
3. **Hypothesis 3: Volatility Contraction During Grinding Drift**
   - *Forensic Test:* In `TRADE_1033_CE`, the trade was held for 6 minutes while spot gained +4.0 pts. In `TRADE_1045_CE`, spot gained +9.1 pts.
   - In both cases, the market transitioned from rapid expansion into a slow upward grind. Option prices failed to expand proportionally, and the trailing exit liquidated on the first minor pullback.

### Recommendation on Trailing Stops:
- **Do NOT implement the hardcoded +12 pt trailing threshold yet.**
- As mandated, changing trailing rules must remain isolated in research until tested against historical baseline distributions to avoid introducing new lookahead or curve-fitting.

---

## 4. Reusable Architecture & Deterministic QA (Reviewer D)

To ensure code excellence and portability:
1. **Extracted Module:** Created [`core/session_chop_circuit_breaker.py`](file:///private/tmp/tradebot-sentinel-quant-audit/core/session_chop_circuit_breaker.py).
2. **Full State Persistence & Recovery:** Implemented `to_dict()` and `from_dict()` for atomic integration with APM WAL snapshots.
3. **Deterministic Replay Guarantee:** Validated that identical event sequences produce identical permission outputs across independent instances.
4. **Test Suite:** [`test_session_chop_circuit_breaker_standalone.py`](file:///private/tmp/tradebot-sentinel-quant-audit/research/sentinel_quant_audit_v2/tests/test_session_chop_circuit_breaker_standalone.py) (5 passed in 0.16s).

---

## 5. Final Synthesis & Verdict

| Dimension | Baseline Sentinel | Challenger (Chop Breaker $L=2$) | Status / Scientific Verdict |
| :--- | :--- | :--- | :--- |
| **Mechanics** | Churns continuously in chop (9 trades on Oct 14) | Halts after 2 consecutive stop-outs | **CONFIRMED STRUCTURAL IMPROVEMENT** (Prevents uncontrolled churn) |
| **Profitability** | -Rs 106.62 | +Rs 2,458.67 | **UNVERIFIED SAMPLE ARTIFACT** (Heavily dependent on Oct 14 loss order) |
| **Causality** | Clean | Clean, lookahead-free | **VERIFIED** |
| **Live Readiness**| Not certified | Not certified | **RESEARCH & SHADOW ONLY** |

### Official Verdict:
$$\mathbf{CHALLENGER\_CONDITIONALLY\_VALIDATED\_FOR\_PARALLEL\_SHADOW}$$
**The Session Chop Circuit Breaker is scientifically validated as an effective risk filter against over-trading in chop, but its reported positive P&L must NOT be treated as guaranteed live alpha. Parallel shadow observation must continue without live orders.**
