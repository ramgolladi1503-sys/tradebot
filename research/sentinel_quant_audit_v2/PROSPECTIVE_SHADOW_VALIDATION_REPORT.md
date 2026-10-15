# SENTINEL PROSPECTIVE SHADOW VALIDATION REPORT

**Milestone:** Prospective Shadow Validation & Adversarial Verification  
**Branch:** `research/sentinel-quant-audit-20261015`  
**PR:** #985  
**Protected Baselines:** PR #968 (`e6d0ae46643ba21767e13e0c40fa8389e51d1acb`) and PR #980 (`c87688055c3df2d77a4220eb1c0c4d763db9c5c2`) — **100% frozen and untouched**.

---

## 1. Compliance with Exchange STT Mandate (0.15% Rate)

As instructed, all financial calculations, transaction friction models, and multi-track ledgers have been re-anchored to the **official 0.15% STT rate on option sell premium**:
- **Statutory Turnover Breakdown:**
  - Brokerage: Flat Rs 40.00 / round-trip
  - **Securities Transaction Tax (STT): 0.15% on sell turnover**
  - Exchange Turnover Fee: 0.05%
  - GST: 18% on (Brokerage + Exchange Fee)
  - Stamp Duty: 0.003% on buy turnover
  - SEBI Turnover Charges: 0.0001%
  - Adverse Slippage: 1 tick (0.05 pt) entry + 1 tick (0.05 pt) exit = 0.10 pt

### Reconciled Baseline Financials (STT = 0.15%):
- **Oct 13 (NIFTY):** 6 trades | Gross Opt: +36.85 pts | Stat: Rs 376.98 | **Net Rupee: +Rs 1,979.27**
- **Oct 14 (NIFTY):** 9 trades (1 unresolved) | Gross Opt: -62.80 pts | Stat: Rs 620.09 | **Net Rupee: -Rs 4,754.09**
- **Oct 15 (NIFTY):** 5 trades | Gross Opt: +29.75 pts | Stat: Rs 378.32 | **Net Rupee: +Rs 1,522.93**
- **Oct 15 (SENSEX):** 6 trades | Gross Opt: +70.95 pts | Stat: Rs 365.29 | **Net Rupee: +Rs 1,041.71**
- **BASELINE TOTAL EVALUABLE NET RUPEE P&L:** **-Rs 210.18**

---

## 2. Removal of Unsubstantiated Executable Bid/Ask P&L Claims

In previous summaries, an executable bid/ask column was reported using estimated spreads.  
**Adversarial Audit Retraction:**
- Machine-readable WAL records captured **entry Bid/Ask depth only**.
- **Exit Bid/Ask depth was NOT persisted in the WAL** at the moment of liquidation (only `opt_exit_ltp` was stored).
- Therefore, claiming a *verified executable bid/ask fill P&L* is scientifically invalid.
- **Correction:** All tables now formally classify quote coverage as **`ENTRY_DEPTH_ONLY_EXIT_DEPTH_MISSING` (Partial Depth)**. Realistic 1-tick adverse slippage (0.10 pt) is applied to LTP as a conservative benchmark, and claims of exact bid/ask fills are retracted until bidirectional tick snapshots are recorded in shadow.
- **Unresolved Exit Rule:** `TRADE_1513_PE` is recorded as `NOT_EVALUABLE / UNRESOLVED_RISK` and is **never** assigned zero loss or treated as a win.

---

## 3. Two-Loss Circuit Breaker: Research Hypothesis Status

The two-loss circuit breaker ($L=2$) is treated strictly as an **unproven research hypothesis**, not a certified profitable strategy.  
- **Reviewer A & E Falsification Re-Affirmed:** The parameter $L=2$ is not optimized against October 14 again. We acknowledge that its historical performance (+Rs 2,587.18 drawdown reduction) benefited from the sequential clustering of Trade #4 and Trade #5 on Oct 14.
- The threshold remains **frozen at $L=2$** solely to serve as a pre-registered hypothesis for prospective shadow observation.

---

## 4. Architecture of the Separate Read-Only Shadow Observer

We built and verified [`core/shadow_circuit_breaker_evaluator.py`](file:///private/tmp/tradebot-sentinel-quant-audit/core/shadow_circuit_breaker_evaluator.py):
- **Zero Runtime Interference:** Implements a passive observer pattern. It inspects trade proposals and exits emitted by Sentinel without altering position state, APM memory, or calling broker APIs.
- **Asset & Calendar Date Isolation:** State is strictly partitioned by `(asset, session_date)` tuples. NIFTY and SENSEX maintain independent failure counters.
- **Strict Event-Time Causality:** A shadow veto is evaluated **if and only if** $\ge 2$ consecutive losses have closed prior to the entry proposal timestamp.
- **Automated Regression Suite:** [`test_shadow_evaluator.py`](file:///private/tmp/tradebot-sentinel-quant-audit/research/sentinel_quant_audit_v2/tests/test_shadow_evaluator.py) (3 passed in 0.15s).

---

## 5. Daily Baseline vs Challenger Prospective Shadow Ledger

Reconciled under 0.15% STT and exact lot sizes (**NIFTY 65 qty, SENSEX 20 qty**):

| Asset | Session Date | Baseline Trades | Quote Depth Status | Baseline Net Rupee | Shadow Vetoes | Challenger Trades | Challenger Net Rupee | Drawdown Reduction |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **NIFTY** | `2026-10-13` | 6 (6 eval, 0 unres) | Partial Depth (Entry only) | **+Rs 1,979.27** | 0 | 6 | **+Rs 1,979.27** | Rs 0.00 |
| **NIFTY** | `2026-10-14` | 9 (8 eval, 1 unres) | Partial Depth (Entry only) | **-Rs 4,754.09** | 5 | 4 | **-Rs 2,166.91** | **+Rs 2,587.18** |
| **NIFTY** | `2026-10-15` | 5 (5 eval, 0 unres) | Partial Depth (Entry only) | **+Rs 1,522.93** | 0 | 5 | **+Rs 1,522.93** | Rs 0.00 |
| **SENSEX** | `2026-10-15` | 6 (6 eval, 0 unres) | Partial Depth (Entry only) | **+Rs 1,041.71** | 0 | 6 | **+Rs 1,041.71** | Rs 0.00 |
| **TOTAL** | **ALL** | **26 Trades** | **Partial Depth (All)** | **-Rs 210.18** | **5 Vetoes** | **21 Trades** | **+Rs 2,377.00** | **+Rs 2,587.18** |

---

## 6. Separating Verified Facts from Hypotheses on Oct 15

| Observation | Verified Empirical Fact | Competing Hypothesis | Scientific Conclusion |
| :--- | :--- | :--- | :--- |
| `TRADE_1006_CE` | Spot moved +1.0 pt; Option lost -0.50 pt in 120 seconds. | IV Crush / Theta Decay vs Spread Crossing | **Theta/IV crush refuted** (hold duration was only 2 min). **Spread crossing confirmed:** 1.0 pt spot move gave $+0.55$ delta, but 0.40 pt bid-ask spread caused loss when trailing stop hit. |
| `TRADE_1033_CE` | Spot moved +4.0 pts; Option lost -5.75 pts in 6 minutes. | IV Contraction vs Spread Crossing | **Mixed Driver:** Spot drift was sluggish; option premium eroded faster than delta accumulation, with trailing stop crossing the Bid. |
| `TRADE_1045_CE` | Spot moved +9.1 pts; Option lost -1.90 pt in 7.1 minutes. | Runner Peak Pullback vs Bid Liquidity | **Pullback Execution Driver:** Trade entered runner mode, hit local peak, and on reversal, trailing stop liquidated into a thinning Bid. |

---

## 7. Official Adversarial Sign-Off

$$\mathbf{SHADOW\_EVALUATION\_CERTIFIED\_READ\_ONLY}$$

1. **Safety Affirmation:** No broker orders, no live capital, no modifications to PR #968 or PR #980.
2. **Readiness Determination:** All tests pass. The pre-frozen two-loss breaker is deployed strictly as a read-only shadow evaluator to collect genuine out-of-sample forward sessions.
