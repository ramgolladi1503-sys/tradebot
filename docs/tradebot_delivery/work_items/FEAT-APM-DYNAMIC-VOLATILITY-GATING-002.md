# Work Item: FEAT-APM-DYNAMIC-VOLATILITY-GATING-002

## Adaptive ATR Targets, Chandelier Volatility Trailing Stops, Option Writer Open Interest (OI) Confirmation, and Session Frequency Governance

**Work Item ID**: `FEAT-APM-DYNAMIC-VOLATILITY-GATING-002`  
**Classification**: `FEATURE / QUANT_EXECUTION_ENHANCEMENT`  
**Status**: `GOVERNANCE_REVIEW`  
**Branch**: `feat/apm-dynamic-vol-oi`  
**Worktree**: `/private/tmp/tradebot-apm-dynamic-vol-oi`  
**Trading Safety Status**: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `status=NO_CERTIFIED_EDGE`

---

## 1. Problem Statement & Quantitative Motivation
- **Empirical Failure on October 19 Session**:
  - The strategy correctly identified the macro PE breakdown with 100% directional accuracy. Deep PE strikes (`NIFTY 23000 PE`, `SENSEX 74000 PE`) rallied +100 to +111 points.
  - However, Sentinel recorded **17 churned trades, -₹1,432.01 Net PnL**, and **₹1,535.01 in statutory frictional drag**.
  - **Root Causes**:
    1. *Hardcoded Target and Leash Fallacy*: Hardcoded 15/30 points and a static 12-point trailing stop choked trades during normal 1-minute candle pullbacks.
    2. *Spot vs Option Duality Conflict*: Exiting on microscopic spot ticks forced option exits at wide bid-ask spreads (-10 to -15 pts option loss despite positive spot gain).
    3. *Blindness to Option Writers*: Lacked confirmation from Call/Put Open Interest (OI) positioning.
    4. *Unchecked Churning*: Taking 17 entries in the same zone bled ₹1,535 in statutory charges.

---

## 2. Business Analysis (BA Pass)
- **Functional Requirements**:
  - `FR-01`: Replace hardcoded 15/30 points with dynamic ATR-scaled targets ($1.5 \times \text{ATR}$ Scalp, $3.5 \times \text{ATR}$ Runner).
  - `FR-02`: Chandelier Volatility Trailing Stop on Option High-Water Mark ($\text{HWM} - \max(25.0, 2.5 \times \text{ATR} \times \Delta)$).
  - `FR-03`: Real-Time Institutional Writer Radar tracking Call Writer additions ($\Delta \text{OI}_{\text{CE}} > 0$) and Put Writer panic unwinding ($\Delta \text{OI}_{\text{PE}} < 0$).
  - `FR-04`: Session Trade Cap: Maximum 3 to 4 trades per index per session.
  - `FR-05`: Time-of-Day Lunch Freeze: No new entries between 11:15 IST and 13:30 IST.

---

## 3. Product Owner (PO Pass)
- **Measurable Acceptance Criteria**:
  - `AC-1`: Target 1 and Target 2 adapt dynamically across NIFTY (15/40 pts) and SENSEX (45/115 pts).
  - `AC-2`: Chandelier trailing stop survives a simulated 15-point option dip while locking in macro gains once $+2.5 \times \text{ATR}$ is reached.
  - `AC-3`: Writer OI confirmation vetoes breakdowns where Call Writers are shedding Open Interest.
  - `AC-4`: The 5th entry attempt in any single session is rejected fail-closed with `SESSION_TRADE_CAP_REACHED`.
  - `AC-5`: Strict read-only safety invariant verification (`read_only=true`, `is_order_action=false`, `broker_api_called=false`).

---

## 4. The 6-Attacker Red Team Gauntlet (100 Adversarial Attack Vectors)

### Attacker 1: The Microstructure & Slippage Adversary (20 Vectors)
1. What happens if SENSEX option spread widens to 8 points on a fast market breakdown?
2. Does the Chandelier stop exit at Ask or Bid? If Bid, does slippage exceed the 2.5 ATR cushion?
3. What if an option tick arrives out of sequence with an exchange timestamp from 5 seconds ago?
4. How does the ATR multiplier handle zero or negative ATR during illiquid market opens?
5. Does the trailing stop ratchet down if the underlying price spikes temporarily due to a fat finger?
6. What if the Bid-Ask spread ratio exceeds 4.0% while Chandelier SL is breached?
7. Does the runner mode allow partial fills, or assume 100% execution at quote?
8. Can an aggressive market buy lift the offer and artificially inflate the Option HWM?
9. How does the model account for Exchange turnover charge tiers between BSE and NSE?
10. What happens if Upstox drops quote packets during peak volatility?
11. Does the model penalize strike selection if open interest is under 100,000 contracts?
12. How does the system handle strike illiquidity during deep OTM to ITM transitions?
13. If spot moves 50 points in 1 second, does the option price model lag behind?
14. Is the friction drag subtracted before or after calculating the Target 1 breakeven point?
15. What if the option tick has high LTP but zero volume in the 1-minute window?
16. Does the Chandelier cushion expand proportionally with India VIX spikes?
17. How does the model handle tick batching where 5 ticks arrive in a single WebSocket frame?
18. Can the trailing stop trigger twice if two identical ticks arrive consecutively?
19. Does the system support lot-size normalization between NIFTY (lot 75/25) and SENSEX (lot 10)?
20. Does a wide cushion cause catastrophic loss if an exchange trading halt occurs?

### Attacker 2: The Open Interest & Derivatives Quant Adversary (20 Vectors)
21. What if Upstox broadcasts Open Interest updates only once every 3 minutes?
22. Does the Writer Radar calculate $\Delta \text{OI}$ from day start or rolling 15-minute windows?
23. What if Call OI increases purely due to short covering on an inverted strike?
24. How does the system distinguish retail call buying from institutional call writing?
25. Can a high PCR give a false bullish signal in an extreme bear trending regime?
26. What happens to OI calculations during expiry day rollover (contract migration)?
27. Does the model handle 0-DTE option delta non-linearities (rapid gamma expansion)?
28. What if the nearest OTM strike has high OI, but the ITM strike has zero OI?
29. Does the model verify that Put Writer unwinding is accompanied by volume expansion?
30. How does the system handle split strikes (e.g. 50-pt strikes on NIFTY vs 100-pt strikes on SENSEX)?
31. What if Call OI is massive but located 500 points away from spot (irrelevant wall)?
32. Does the model track Cumulative Volume Delta (CVD) alongside OI?
33. How is the Option Delta $\Delta$ calculated—Black-Scholes-Merton or empirical tick ratio?
34. If implied volatility collapses after an event, does the option stop trigger prematurely?
35. What if a strike has negative OI reported due to exchange reconciliation bugs?
36. Does the model normalize OI by total index open interest?
37. How does the model handle Far-Month vs Near-Month writer positioning?
38. Can market makers manipulate 5-level depth during the 11:00 AM lull to fake imbalance?
39. What if Call Writers are adding, but Put Writers are ALSO adding aggressively (straddle writing)?
40. Does the model detect Gamma Flip levels where dealers switch from stabilizing to accelerating?

### Attacker 3: The Causal & Time-Series Leakage Adversary (15 Vectors)
41. Does the ATR calculation look ahead into the current 1-minute candle's close?
42. Is the Opening Range High/Low strictly causal and frozen at 09:45:00.000 IST?
43. Does the Writer Radar use future ticks when computing rolling $\Delta \text{OI}$?
44. Are bootstrap confidence intervals resampled with block continuity or IID?
45. Does the multi-session replay leak post-market settlement prices into intra-day exits?
46. Is the 11:15–13:30 Lunch Freeze evaluated on monotonic clock or system wall clock?
47. What if the system clock drifts by 2 seconds relative to exchange timestamps?
48. Does the backtest assume fill at the signal bar close or next tick open?
49. Are frictional fees deducted contemporaneous with the tick or batch-processed at EOD?
50. Does the Chandelier HWM track only ticks seen AFTER entry timestamp?
51. What happens if a tick has an exchange timestamp older than the entry time?
52. Is the regime gear (Gear 1 vs Gear 2) computed causally without smoothing lag?
53. Does the option selection algorithm know which strike will be the biggest winner in advance?
54. Can lookahead occur if parquet chunks are read out of lexical sort order?
55. Does the trade aggregator filter out in-flight trades from completed stats properly?

### Attacker 4: The Concurrency, Fault Tolerance & Recovery Adversary (15 Vectors)
56. What happens if the APM process crashes while holding a live position?
57. Does the WAL recovery re-arm the Chandelier stop with the correct peak HWM from disk?
58. What if the WAL JSON file is truncated due to a power outage mid-write?
59. Are atomic write-rename mechanics (`tempfile -> rename`) used for all WAL updates?
60. What happens if two threads attempt to update the APM state concurrently?
61. If the WebSocket disconnects for 15 seconds, does APM liquidate or hold?
62. Does the persistence queue drop ticks if the disk becomes 100% full?
63. Can Streamlit UI auto-refresh trigger a race condition with APM tick evaluation?
64. How does the system handle SIGTERM signals sent by systemd or process managers?
65. What if the system runs out of memory (OOM) during heavy 10,000 tick/sec bursts?
66. Is the Option Writer Radar thread-safe when accessed by the dashboard renderer?
67. What happens if the Level-5 depth queue saturates beyond 10,000 items?
68. Does the Chandelier stop recover gracefully if historical ticks are missing on restart?
69. Are file locks used to prevent multiple dashboard instances from corrupting the WAL?
70. Does a crash during `STATE_EXIT_PENDING` leave the system in an unrecoverable zombie state?

### Attacker 5: The Overfitting, P-Hacking & Statistical Validity Adversary (15 Vectors)
71. Is 2.5 ATR overfitted to October 19's specific price action?
72. What happens to the Chandelier stop on a low-volatility day where ATR drops to 4 points?
73. Did we test the 3-4 trade cap across losing regimes to verify it doesn't clip recovery trades?
74. Does the strategy survive a 10-day losing streak without catastrophic account drawdown?
75. Is the Holm-Bonferroni correction applied when testing multiple ATR parameter sets?
76. Does the model assume symmetric behavior for CE and PE legs (put skew bias)?
77. What is the sample size of trades audited—is 38 trades sufficient for statistical power?
78. Could the +100 point PE move be a 3-sigma black swan event that rarely repeats?
79. How does the strategy perform in 2024 and 2025 historical data under different VIX regimes?
80. Does the model account for survivor bias in historical option strike data?
81. Are the bootstrap 95% confidence intervals wide enough to reflect small-sample uncertainty?
82. What happens if market volatility shifts permanently due to regulatory lot size changes?
83. Does the profit factor remain above 1.5 when 2x slippage is injected?
84. Is the lunch freeze optimal across all days of the week or only Mondays?
85. Does the strategy fail closed and report `NO_CERTIFIED_EDGE` until 200+ trades are logged?

### Attacker 6: The Operational, Regulatory & Safety Adversary (15 Vectors)
86. Does any part of this code contain API keys, broker tokens, or account IDs?
87. Can this code accidentally place a live order on Upstox if a configuration flag is toggled?
88. Does the code enforce `read_only = True` in all runtime execution paths?
89. Are broker write endpoints completely absent from the imported libraries?
90. What if an operator accidentally runs `scripts/run_live.sh`? Does the boot guard block it?
91. Does the dashboard display the mandatory `NO_CERTIFIED_EDGE` reputational warning?
92. Are all financial claims backed by cryptographic hashes and raw parquet ticks?
93. Does the system adhere to SEBI algo trading guidelines regarding unauthorized order generation?
94. Are log files purged of any personal identifiable information (PII)?
95. Can an operator override the 4-trade session cap via the Streamlit UI? (Must be blocked).
96. Does the system prevent trading after 15:15 IST (pre-market close auto-squaring)?
97. What happens if an unauthenticated user accesses port 8503? Is execution possible? (No).
98. Are all state changes audited with UTC and IST timestamps?
99. Does the codebase maintain documentation integrity and preserve existing comments?
100. Does this feature touch any forbidden core files (`core/execution*`, `core/broker*`, `main.py`)?

---

## 5. The 3 Reviewers (Formal Invariant Specifications)

### Reviewer 1: Hermes (Institutional Architecture & Invariant Specifications)
- **Invariant H-1**: ATR targets and Chandelier stops must be strictly scale-invariant across NIFTY and SENSEX.
- **Invariant H-2**: Open Interest tracking must run asynchronously and update via an in-memory coalescing map with $O(1)$ lookup time.
- **Invariant H-3**: All exits must use the Option Bid price from Level-5 depth, strictly preventing phantom spot-gain fills.

### Reviewer 2: GSD Implementation Lead (Deterministic Execution & Scoping)
- **GSD Scope**:
  - `core/analytics/writer_oi_analyzer.py` (New): Clean, decoupled Open Interest & PCR analytics module.
  - `core/active_position_manager.py` (Edit): Dynamic ATR targets, Chandelier trailing stop, session trade cap.
  - `tests/unit/test_apm_dynamic_volatility_and_oi.py` (New): Comprehensive deterministic pytest suite covering all 100 attack vectors.
  - Zero touch to forbidden runtime wiring or broker files.

### Reviewer 3: Technical & Quant Analyst (Statistical Rigor & Safety Verification)
- **Quant Audit**:
  - Verify that `NO_CERTIFIED_EDGE` is maintained across all reports.
  - Ensure that bootstrap confidence intervals accurately reflect small-sample variance.
  - Confirm that fee models include STT, GST, SEBI turnover, and bid-ask spread crossing.

---

## 6. The 2 Final Approvers (Senior Governance & Sign-Off)
- **Approver 1: Senior QA Lead** (Mandate: Must verify 100% test pass rate, zero regression, and complete answer satisfaction from all 3 Reviewers on the 100 attack questions).
- **Approver 2: Chief Risk Officer / Product Owner** (Mandate: Must verify zero live broker wiring, strict preservation of capital, and adherence to non-negotiable trading safety rules).
