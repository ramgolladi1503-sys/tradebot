# Hypothesis Inventory

## HYP-1: Mean Reversion on SPY
- **Author**: quant_1
- **Created**: 2026-06-27T06:51:24.334396
- **Description**: SPY mean reverts after 3 down days.

## External Corpus Ingestion — 2026-08-27

Authoritative detail: `docs/research_registry/13_external_hypothesis_corpus_20260827.md`

### QuantConnect
- `QC-H01` Multi-market relative-price dislocation / information propagation
- `QC-H02` Opening impulse continuation
- `QC-H03` Futures return × volume × OI exhaustion
- `QC-H04` Adaptive range breakout / Dual Thrust
- `QC-H05` Volatility-adaptive breakout memory
- `QC-H06` VIX / implied-volatility conditioned movement
- `QC-H07` Expiry-calendar effect
- `QC-H08` Intraday relative-value / pairs state

### Quantocracy
- `QCY-H01` Price-path convexity / path shape
- `QCY-H02` Cross-market information propagation
- `QCY-H03` Continuation vs exhaustion path interaction

### Davey / Kaufman / Carver
- `DKC-H01` Intraday path/noise efficiency state
- `DKC-H02` Adaptive lookback by noise/volatility state
- `DKC-H03` Path efficiency × dispersion shock
- `DKC-H04` Turnover-adjusted forecast selection
- `DKC-H05` Diversification by mechanism
- `DKC-H06` Futures basis state as conditional information

### r/algotrading
- `RED-H01` First retest vs repeated touch with randomized controls
- `RED-H02` Regime-conditional strategy activation
- `RED-H03` Volatility contraction → future magnitude
- `RED-H04` Next-causal-slice execution sensitivity
- `RED-H05` Fill-quality reconciliation
- `RED-H06` Cost headroom
- `RED-H07` Diversification by mechanism
- `RED-H08` Failed reversal as regime-transition information
- `RED-H09` Causal mechanism / ML search-pressure governance
- `RED-H10` Profit-concentration kill test

### r/Trading
- `TRD-H01` Context-conditioned setup value
- `TRD-H02` Context-first discovery
- `TRD-H03` Relative resilience/weakness versus broader index
- `TRD-H04` Large-move continuation vs exhaustion

### r/Daytrading
- `DAY-H01` Local sweep/rejection conditioned on higher-timeframe state
- `DAY-H02` Sweep without cross-market confirmation as reversal candidate

All external entries remain hypotheses or governance candidates. No entry in this section is certified as profitable, OOS-supported, execution-viable, or structural edge.