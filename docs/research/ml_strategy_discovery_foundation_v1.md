# ML Strategy Discovery Foundation v1

## Decision

`FOUNDATION_IMPLEMENTED_DATA_INTEGRATION_PENDING`

This change creates an offline, research-only foundation for discovering and extracting deterministic strategy hypotheses. It does **not** claim structural edge, profitability, backtest success, walk-forward success, or production readiness.

## Agent work contract

```text
source_agent: ChatGPT
action: GENERATE_PATCH
title: ML strategy discovery foundation v1
scope: data-independent contracts, causal labels, chronological validation, interpretable models, rule extraction, negative controls, candidate registry, and independent audit
requested_paths: research/ml_strategy_discovery, scripts/audit_ml_strategy_discovery_foundation.py, tests/test_ml_strategy_discovery_*, docs/research/ml_strategy_discovery_foundation_v1.md
allowed_paths: same as requested_paths
forbidden_paths: main.py, run_live.sh, config/, credentials.py, core/execution*, core/broker*, core/order*, core/risk*, core/feed*, strategies/, dashboard/, runtime/live*, .env, *.env, secrets*
expected_tests: focused pytest files plus full pytest in CI
acceptance_proof: deterministic tests, fail-closed safety envelope, strict future-only labels, non-overlapping chronological partitions, locked-holdout audit, and no runtime/broker imports
```

## Implemented

1. **Causal observation contract**
   - Every timestamp must be timezone-aware.
   - Every feature carries `available_at` and `source`.
   - `available_at > decision_at` fails closed.
   - `future_*` and `target_*` feature names are forbidden.
   - NaN and infinity are rejected.

2. **Path-dependent triple-barrier labels**
   - Entry is the first bar whose start is strictly after the decision timestamp.
   - Supports LONG and SHORT.
   - Target-first, stop-first, neither, and no-legal-entry outcomes.
   - A same-bar target/stop collision is conservatively `STOP_FIRST` and explicitly marked ambiguous.
   - MFE and MAE are retained.

3. **Chronological research partitions**
   - Development, validation, and locked holdout are disjoint and ordered.
   - Anchored walk-forward folds support an explicit purge gap.
   - Random time-series shuffling is not provided.

4. **Interpretable model adapters**
   - Depth-limited sklearn decision tree.
   - Deterministic CPU XGBoost adapter.
   - Both require binary classes and rectangular data.
   - Neither reads holdout data, persists a model, activates a model, or changes runtime behavior.

5. **Readable rule extraction**
   - Extracts positive leaf paths from a fitted shallow tree.
   - Returns explicit feature/operator/threshold conditions, support, and probability.

6. **Negative controls**
   - Version-independent deterministic label permutation.
   - Delayed feature series.
   - Parameter-neighborhood generation.
   - Deterministic randomized entry offsets.

7. **Research candidate contract and registry**
   - Candidate dossier contains hypothesis, regime, event sequence, entry, invalidation, exit, support, dataset hash, and safety claims.
   - Registry has no LIVE or executable status.
   - Status transitions require evidence hashes and remain research/shadow-only.

8. **Independent audit contracts**
   - Observation audit detects leakage, malformed data, duplicates, and inconsistent schemas.
   - Candidate audit detects overlap, chronology failures, empty partitions, and holdout consumption.

## Mandatory safety boundary

Every discovery artifact is required to preserve:

```text
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
```

The package has no imports from broker, order, execution, risk, feed, dashboard, live runtime, or production strategy modules.

## Not implemented because authoritative data is not yet bound

- TradeBot-specific underlying candle adapter.
- Historical option quote/depth/spread adapter.
- Timestamp-alignment contract against selected source files.
- Actual feature computation from those sources.
- Model training results.
- SHAP interaction analysis.
- Candidate strategy discoveries.
- OptionBacktestEngine integration.
- Costs, slippage, fill probability, or Profit Factor analysis.
- WFA results or locked-holdout result.
- Any structural-edge or profitability claim.

Implementing or claiming those without identifying and freezing the authoritative datasets would be fake progress.

## Validation commands

```bash
pytest -q \
  tests/test_ml_strategy_discovery_contracts.py \
  tests/test_ml_strategy_discovery_labels_models.py

python scripts/audit_ml_strategy_discovery_foundation.py
pytest -q
```

The standalone audit's correct result before data integration is:

```text
FOUNDATION_IMPLEMENTED_DATA_INTEGRATION_PENDING
NO_EDGE_OR_PROFITABILITY_CLAIM
```

## Next data-bound phase

The next PR should do only the following:

1. inventory and hash authoritative underlying and options datasets;
2. document timestamp semantics, timezone, cadence, missing-session policy, and depth tolerance;
3. implement one adapter into `DiscoveryObservation`;
4. independently audit row conservation, timestamp alignment, feature availability, and determinism;
5. keep the locked holdout inaccessible to discovery code.

Only after that gate passes should model fitting and rule discovery begin.
