# External Hypothesis Corpus — 2026-08-27

## Authority and Scope

Repository authority for this ingestion was frozen at:

- base branch: `main`
- base SHA: `e8240c67e01f1abd7a59b1d1c2033f7e675cf81f`
- ingestion branch: `research/external-corpus-ingestion-20260827`

This file preserves externally sourced mechanisms and research-governance ideas for later TradeBot/MROS validation. It does **not** certify profitability, structural edge, execution viability, or live readiness.

Default safety state for all entries:

- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_authorized=false`

## Evidence Hierarchy

1. Primary / near-primary: NSE, SEBI, peer-reviewed or primary academic papers.
2. Structured research libraries: Quantpedia, QuantConnect.
3. Indian systematic implementation sources: Definedge, Zerodha.
4. Continuous quant discovery: Quantocracy.
5. Named methodology/mechanism sources: Kevin Davey, Perry Kaufman, Robert Carver.
6. Practitioner discovery: Reddit / TradingView / YouTube / blogs.
7. TradeBot immutable data and reproducible repository evidence outrank all external summaries.

External sources are hypothesis inputs only unless separately validated.

---

# Source Batch A — QuantConnect

Source: `https://www.quantconnect.com/learning/articles/investment-strategy-library`

Source role: `HIGH_QUALITY_HYPOTHESIS_SOURCE`

Relevant normalized mechanisms:

| ID | Mechanism | Indian-index translation | Disposition |
|---|---|---|---|
| QC-H01 | Multi-market relative-price dislocation / information propagation | NIFTY futures ↔ spot ↔ NIFTYBEES ↔ constituents | `READY_FOR_SPEC` |
| QC-H02 | Opening impulse continuation | 09:15–09:30 opening state → later causal return/range | `READY_FOR_SPEC` |
| QC-H03 | Futures return × volume × OI exhaustion | distinguish informed continuation from covering/exhaustion | `READY_FOR_SPEC` |
| QC-H04 | Adaptive range breakout / Dual Thrust | recent causal range → dynamic breakout thresholds | `READY_FOR_SPEC` |
| QC-H05 | Volatility-adaptive breakout memory | volatility state → relevant breakout lookback | `RELATED_BUT_DISTINCT` |
| QC-H06 | VIX / implied-volatility conditioned movement | India VIX state/change → future range/direction conditional tests | `READY_FOR_SPEC` |
| QC-H07 | Expiry-calendar effect | Indian DTE / expiry-state conditioning | `DATA_SUITABILITY_REVIEW` |
| QC-H08 | Intraday relative-value / pairs state | NIFTY/BANKNIFTY/SENSEX/futures relative dislocation | `READY_FOR_SPEC` |

Do not copy foreign-market parameters, horizons, or asset assumptions directly.

---

# Source Batch B — Quantocracy

Source: `https://quantocracy.com/`

Source role: `HIGH_VALUE_DISCOVERY_SOURCE`

Quantocracy is treated as an aggregator. For any candidate promoted beyond hypothesis stage, retrieve and preserve the original paper/article where possible.

Relevant normalized mechanisms / methods:

| ID | Mechanism / method | TradeBot translation | Disposition |
|---|---|---|---|
| QCY-H01 | Price-path convexity / path shape | test whether full path geometry adds information beyond net return/range | `READY_FOR_SPEC` |
| QCY-H02 | Cross-market information propagation | multivariate NIFTY futures/spot/BANKNIFTY/SENSEX/constituent state | `READY_FOR_SPEC` |
| QCY-H03 | Continuation vs exhaustion path interaction | same displacement, different path/state → different outcome | `READY_FOR_SPEC` |
| QCY-G01 | Control-group / placebo design | matched/randomized controls mandatory for event-pattern studies | `GOVERNANCE_CANDIDATE` |
| QCY-G02 | Search-complexity / overfitting controls | record feature, parameter, horizon and strategy search pressure | `GOVERNANCE_CANDIDATE` |
| QCY-G03 | Transaction-cost/capacity stress | nonlinear costs and capacity as separate economic gates | `GOVERNANCE_CANDIDATE` |

---

# Source Batch C — Davey / Kaufman / Carver

## Kevin Davey

Role: `RESEARCH_PROCESS_AND_VALIDATION_SOURCE`

Preserved concepts:
- bounded feasibility testing before broad optimization
- walk-forward as distinct evidence
- Monte Carlo / path uncertainty
- incubation / forward observation
- realistic cost assumptions
- explicit monitoring and quit criteria
- complexity restraint

## Perry Kaufman

Role: `ADAPTIVE_MECHANISM_SOURCE`

Preserved concepts:
- Efficiency Ratio / directional path efficiency
- adaptive lookback / adaptive filtering
- trend-vs-noise state separation

## Robert Carver

Role: `RISK_TURNOVER_PORTFOLIO_METHOD_SOURCE`

Preserved concepts:
- constant-risk scaling and systematic sizing
- turnover and cost awareness
- diversification by genuinely distinct rules/mechanisms
- futures carry/basis state
- operational engineering as a source of negative alpha when wrong

Normalized candidates:

| ID | Mechanism | Disposition |
|---|---|---|
| DKC-H01 | Intraday path/noise efficiency state | `READY_FOR_SPEC` |
| DKC-H02 | Adaptive lookback by noise/volatility state | `RELATED_BUT_DISTINCT` |
| DKC-H03 | Path efficiency × dispersion shock | `PRIORITY_READY_FOR_SPEC` |
| DKC-H04 | Turnover-adjusted forecast selection | `ECONOMIC_GATE` |
| DKC-H05 | Diversification by mechanism, not parameter variants | `PORTFOLIO_GOVERNANCE` |
| DKC-H06 | Futures basis state as conditional information | `PRIORITY_READY_FOR_SPEC` |

---

# Source Batch D — r/algotrading

Source class: `PRACTITIONER_HYPOTHESIS_SOURCE_ONLY`

The 2026-08-27 pass mined high-signal threads/comments relevant to TradeBot. Reddit P&L, claimed Sharpe, claimed live success, and anecdotes are **not** accepted as evidence.

Normalized candidates / controls:

| ID | Mechanism / control | Disposition |
|---|---|---|
| RED-H01 | First retest vs repeated support/resistance touches with randomized controls | `HIGH_INFORMATION_NEGATIVE_CONTROL_FAMILY` |
| RED-H02 | Regime-conditional strategy activation | `FRAMEWORK` |
| RED-H03 | Volatility contraction predicts magnitude, not necessarily direction | `PRIORITY_READY_FOR_SPEC` |
| RED-H04 | Next-causal-slice execution sensitivity | `MANDATORY_EXECUTION_STRESS` |
| RED-H05 | Theoretical-vs-realized fill reconciliation | `EXECUTION_VALIDATION_FRAMEWORK` |
| RED-H06 | Cost headroom / break-even deterioration | `MANDATORY_ECONOMIC_GATE` |
| RED-H07 | Diversification by mechanism | `PORTFOLIO_FRAMEWORK` |
| RED-H08 | Failed reversal event as regime-transition information | `READY_FOR_SPEC` |
| RED-H09 | ML requires coherent causal mechanism and counted feature-search pressure | `GOVERNANCE` |
| RED-H10 | Profit-concentration kill test | `MANDATORY_ROBUSTNESS_GATE` |

Low-information generic indicator recipes are not admitted as independent mechanisms unless they contain materially new structural rationale.

---

# Source Batch E — r/Trading

Source supplied by user as Reddit short link. Short-link resolution did not provide durable post identity through the available web interface, therefore:

`SOURCE_IDENTITY=PARTIAL`

Only mechanism-level observations surfaced during the review are preserved; no author-specific or performance claim is treated as evidence.

| ID | Mechanism / method | Disposition |
|---|---|---|
| TRD-H01 | Same setup can have different expectancy by independently defined regime | `HIGH_PRIORITY_FRAMEWORK` |
| TRD-H02 | Discover repeatable market-state behavior before deriving entry rules | `RESEARCH_METHOD` |
| TRD-H03 | Relative resilience/weakness versus broader index | `READY_FOR_SPEC` |
| TRD-H04 | Large-move continuation vs exhaustion conditioned on path/breadth | `MERGE_WITH_EXISTING_FAMILY` |
| TRD-G01 | Added filters/conditions count as search pressure | `GOVERNANCE` |

---

# Source Batch F — r/Daytrading

Source supplied by user as Reddit short link. Exact post identity was not durably recoverable, therefore:

`SOURCE_IDENTITY=PARTIAL`

Mechanisms surfaced during review:

| ID | Mechanism | Disposition |
|---|---|---|
| DAY-H01 | Local sweep/rejection conditioned on higher-timeframe trend state | `HYPOTHESIS_SOURCE_ONLY` |
| DAY-H02 | Sweep without futures/breadth confirmation as reversal candidate | `HYPOTHESIS_SOURCE_ONLY` |
| DAY-G01 | Reduce human decision-load by ranking fewer higher-quality candidates | `UI_GOVERNANCE_RELATED` |

ICT/FVG/order-block terminology itself is not accepted as evidence of structural edge.

---

# Cross-Source Deduplication and Lineage

The following concepts are related and must **not** be counted as independent discoveries merely because they have different names.

## Family M1 — Information propagation / relative dislocation

Members:
- `QC-H01`
- `QC-H08`
- `QCY-H02`
- `DKC-H06`
- `TRD-H03` (partial overlap)

Canonical mechanism:

> Relative movement across linked markets/instruments may reveal which venue or component currently contains information and whether lagging instruments subsequently catch up or the leader mean-reverts.

Do not collapse all descendants into one test. Preserve materially distinct conditioning variables such as basis, breadth, expiry state, or path efficiency.

## Family M2 — Continuation vs exhaustion

Members:
- `QC-H02`
- `QC-H03`
- `QCY-H03`
- `DKC-H01`
- `RED-H08`
- `TRD-H04`
- `DAY-H01/DAY-H02`

Canonical mechanism:

> Similar observed displacement can have different forward behavior depending on path efficiency, breadth, volume/OI, volatility state, and cross-market confirmation.

## Family M3 — Adaptive breakout / market memory

Members:
- `QC-H04`
- `QC-H05`
- `DKC-H02`

Canonical mechanism:

> Relevant breakout threshold and memory horizon may depend on recent realized range, volatility, and directional efficiency.

## Family M4 — Volatility magnitude prediction

Members:
- `QC-H06`
- `DKC-H03` (interaction)
- `RED-H03`
- existing TradeBot dispersion-shock → volatility-expansion near-miss

Canonical mechanism:

> Volatility/dispersion/contraction state may predict future absolute movement more robustly than direction.

## Family M5 — Research validity and economic survivability

Members:
- `QCY-G01/G02/G03`
- Davey feasibility/WFA/incubation methodology
- `DKC-H04/H05`
- `RED-H04/H05/H06/H09/H10`
- `TRD-G01`

These are research/execution gates, not alpha sources.

---

# Priority Candidate Registry

The following candidates have the best current information-value relative to search pressure. Priority does **not** imply positive expected returns.

| Priority | Candidate | Reason |
|---:|---|---|
| 1 | `DKC-H03` Path efficiency × dispersion shock | attempts to explain an already observed near-miss rather than opening a disconnected family |
| 2 | `DKC-H06` / `QC-H01` basis-conditioned multi-market propagation | structurally plausible and directly relevant to NIFTY futures/spot data |
| 3 | `RED-H03` contraction → future magnitude | tests magnitude separately from direction and aligns with existing evidence |
| 4 | `DKC-H01` causal path efficiency incremental value | low parameter count and easy to falsify |
| 5 | `RED-H08` failed reversal → regime transition | event failure may contain state information; materially distinct from standard trend filters |
| 6 | `RED-H01` first-retest placebo study | strong negative-control design that can kill a common folklore family |

Before any candidate is evaluated, verify actual authoritative data coverage and timestamp semantics.

---

# Mandatory Validation Contract

For any admitted hypothesis:

1. Freeze the economic/structural mechanism.
2. Freeze causal feature definitions and horizons.
3. Verify source-data authority, coverage, units, and timestamps.
4. Audit future leakage.
5. Run bounded DEV feasibility testing first.
6. Record **all** tested variants and search pressure.
7. Run negative/placebo controls.
8. Require parameter-neighborhood and temporal/regime robustness.
9. Freeze before OOS/WFA.
10. Model realistic spread, slippage, fees, taxes, liquidity, and fill timing.
11. Run next-causal-slice execution stress.
12. Run profit-concentration / leave-top-k-out tests.
13. Require independent verification.
14. Use prospective evidence where required.
15. Keep operational correctness, historical evidence, execution viability, and structural-edge certification separate.

Never convert:

- `UNKNOWN -> PASS`
- `MISSING -> ZERO`
- `UNIT_TEST_PASS -> LIVE_PASS`
- `HISTORICAL_PASS -> FORWARD_PASS`
- `CORRELATION -> CAUSATION`
- `BACKTEST_EDGE -> TRADABLE_EDGE`

---

# Explicit Non-Claims

`CORPUS_INGESTED=true`
`VALIDATION_RUN=false`
`HISTORICAL_EDGE_SUPPORTED=false`
`OUT_OF_SAMPLE_SUPPORTED=false`
`EXECUTION_VIABLE=false`
`PROSPECTIVE_SUPPORTED=false`
`STRUCTURAL_EDGE_CERTIFIED=false`

This ingestion preserves research possibilities and governance improvements only.