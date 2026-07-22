# Residual Liquidity Exhaustion Mean Reversion V2 — Stage A Contract

mode: RESEARCH_PATTERN_DISCOVERY_ONLY  
campaign_id: RESIDUAL_LIQUIDITY_EXHAUSTION_MR_V2  
stage: A_HISTORICAL_PATTERN_ATLAS  
base_commit: fa502c07425c67a9f2ba440a20900d772db82689  
execution_allowed: false  
paper_live_allowed: false  
broker_api_called: false

## Objective

Measure whether abnormal cross-index residual displacement historically reverted, and whether an immediate completed-bar sequence of residual contraction plus failed continuation improved that behavior. This stage creates a pattern atlas, not a strategy.

## Frozen hypothesis

For each canonical index, compute its completed 5-minute log return divided by trailing volatility known before that bar. Subtract the mean standardized return of the other available indices. An event occurs when the absolute residual is at least 2.0.

The immediate next completed 5-minute bar is classified as exhaustion-confirmed only when:

- the absolute residual contracts to no more than 50% of the event residual; and
- continuation in the shock direction extends no more than 25% of the event bar range.

Forward reversion is measured at 5, 15, 30 and 60 minutes. No threshold may be changed after outcomes are observed in this run.

## Data boundary

The immutable `upstox-corpus-v1` archive is used only as development/discovery data. It has already been exposed through V1 research, so no date in this corpus may later be described as a fresh final holdout for V2.

Exact authority expected:

- 1,547 candle files;
- 129 quote/depth files;
- 1,676 paired AppleDouble sidecars;
- archive SHA-256 `8c5fd5cded6475347c94f073b3411d6636c34dcc256243270e23ec8daf6b35f7`.

Quote/depth coverage is inventoried but is not used to create a liquidity-exhaustion signal in Stage A. A later depth lane requires a separately frozen synchronization and event-time contract.

## Causality and controls

- Only completed bars are used.
- The event bar cannot influence its own volatility normalizer; rolling volatility is shifted by one bar.
- Confirmation uses only the immediate next completed bar.
- Outcomes cannot cross a session boundary.
- A direction-permutation control shuffles shock direction within symbol and time-of-day buckets while preserving event timestamps and forward-move magnitudes.
- The complete analysis runs twice and semantic outputs must match.

## Outputs

- deterministic event ledger;
- segmented historical metrics by symbol, side, time, magnitude, volatility and calendar period;
- direction-permutation controls;
- quote/depth coverage inventory;
- exact input authority;
- two-run semantic hash manifest;
- development-only summary.

## Result boundary

A successful workflow proves only that the atlas was generated reproducibly from the frozen corpus. It does not prove profitability, structural edge, executable option fills, or paper/live readiness.

The next allowed step is human review of pattern stability. A V2 signal equation must then be frozen in a separate commit before any strategy backtest or WFA begins. New unseen data is required for final confirmation.
