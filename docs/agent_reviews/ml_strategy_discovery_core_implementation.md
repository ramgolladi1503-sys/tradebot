# ML Strategy Discovery Core — Agent Review Evidence

- mode: ML_STRATEGY_DISCOVERY_CORE_V2
- candidate_id: ML_DISCOVERY_CORE_AND_CERTIFIED_SOURCE_ADAPTER
- decision: IMPLEMENTED_PENDING_CURRENT_HEAD_CI_AND_REAL_CORPUS_RUN
- reason: The causal discovery core binds certified source files with explicit start-labelled bar semantics; current-head CI and the local corpus run are required before accepting generated candidates.
- timestamp: 2026-07-21T16:50:00+05:30
- source: ml_strategy_discovery_core_implementation.md
- read_only: true
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: ML strategy discovery core and certified Upstox source adapter
- scope: Implement causal completed-bar discovery, interpretable rule extraction, frozen-rule validation, explicit timestamp authority, and a manifest-bound underlying-data adapter.
- requested_paths: `research/ml_strategy_discovery/`, `scripts/run_ml_strategy_discovery.py`, `tests/test_ml_strategy_discovery_*.py`, and ML-discovery evidence documentation.
- allowed_paths: only the requested research, CLI, focused tests, and evidence paths.
- forbidden_paths: production runtime, configuration, credentials, broker, execution, order, risk, feed, dashboard, production strategies, environment files, secrets, live runtime, and source parquet mutation.
- expected_tests: focused ML-discovery tests, source-adapter negative tests, compile check, full repository tests, health gate, CodeQL, Code Excellence, repo-forensics, evidence gate, registry verification, and gitleaks.
- acceptance_proof: bars become available only at bar end; certified files are contained, hashed, reopened, and session-verified; the imputer and models fit development data only; frozen rules reproduce their source tree leaves; underlying label metrics are never called option P&L.

## Scope Guard

- PRODUCTION FILES TOUCHED: NONE
- STRATEGY FILES TOUCHED: NONE
- RUNTIME WIRING: NONE
- BROKER ADAPTERS TOUCHED: NONE
- RISK OR FEED GATES TOUCHED: NONE
- DASHBOARD FILES TOUCHED: NONE
- CREDENTIAL OR ENVIRONMENT FILES TOUCHED: NONE
- SOURCE PARQUET FILES MUTATED: NONE
- ORDER ACTIONS: NONE
- BROKER API CALLED: NO
- LIVE EXECUTION ENABLED: NO

## Grill Me Review

The first dangerous assumption was that a source timestamp represented a completed decision timestamp. The certified Upstox corpus uses start-labelled one-minute bars. Reading a row's high, low, close, or volume at its start timestamp would leak the candle. The contract now records bar start and bar end separately and uses bar end for decision, feature cutoff, and source-data maximum time.

The second defect involved tree extraction after median imputation. A tree can route a NaN feature with its development-fitted median, while a later rule evaluator might treat the NaN as false. Each frozen rule now carries development imputation values for its path features and is rejected unless its deterministic mask exactly reproduces the source tree leaf.

The third defect was entry-price optimism. Labels now enter at the next legal bar open, include that entry bar in target and stop evaluation, and record the terminal bar end as the time when the outcome becomes known.

Underlying ATR labels remain research proxies. They are not option fills, premium returns, transaction costs, or executable Profit Factor.

## Hermes Review

The source adapter selects certified manifest records and independently verifies contained files. The dataset contract converts source timestamps to completed-bar decision timestamps. Feature and label construction is offline and same-session. Development-only models produce frozen candidate contracts containing side, thresholds, leaf ID, source dataset hash, next-bar-open semantics, and imputation values. Independent evaluation and rule oracles operate only on declared temporal scopes. Strict option replay remains a later, separate authority.

No production inference, ranking, strategy, risk, broker, dashboard, or execution owner imports this package.

## GSD Review

Implemented:

- explicit START and END timestamp semantics
- source timezone and bar interval contracts
- bar-start, bar-end, decision, entry, and terminal timestamps
- strict cadence and finite OHLCV checks
- certified Upstox manifest adapter
- path containment, symlink, SHA-256, byte-size, row-count, schema, symbol, session, and cadence checks
- causal market-structure and event features
- next-legal-bar-open LONG and SHORT labels
- chronological development, validation, and locked holdout partitions
- shallow tree and deterministic CPU XGBoost comparison
- candidate leaf ID, side, dataset hash, and frozen imputation values
- exact candidate-mask versus source-leaf gate
- permutation, timestamp-shift, ablation, parameter, and abstract label-cost controls
- independent future-mutation and rule-mask oracles
- certified-corpus and explicit-file CLI modes
- source, dataset, candidate, and evidence manifests

## QA / Safety Review

The earlier implementation passed functional repository tests but failed evidence and Code Excellence contracts. The repair adds a complete agent review record, literal non-action fields, behavior-focused tests, source-adapter negative controls, executable label timing, and explicit claim boundaries.

Current-head validation must be taken from GitHub workflow results after this document revision. No test count is claimed here before those workflows finish.

## Acceptance Proof

- source candle fields available at a start label: REJECTED
- one-minute start-labelled decision time: SOURCE TIME PLUS ONE MINUTE
- explicit file without timestamp semantics: FAIL CLOSED
- irregular certified cadence: FAIL CLOSED
- path outside certified root: FAIL CLOSED
- symlinked source component: FAIL CLOSED
- SHA or byte-size disagreement: FAIL CLOSED
- incomplete source session: FAIL CLOSED
- source symbol or date disagreement: FAIL CLOSED
- future mutation changes current features: FAIL CLOSED BY TEST
- label entry: NEXT LEGAL BAR OPEN
- label terminal availability: TERMINAL BAR END
- same-bar target and stop: EXPLICIT AMBIGUITY, CONSERVATIVE STOP VALUE
- next-session gap satisfies intraday label: PROHIBITED
- model imputer fitted outside development: PROHIBITED
- candidate without frozen imputation evidence: REJECTED BY LEAF REPRODUCTION
- extracted rule differs from source leaf: FAIL CLOSED
- holdout fitted or validation-scored by discovery model: PROHIBITED
- option profitability inferred from underlying labels: PROHIBITED
- executable or live candidate state: ABSENT

## Runtime Proof Required After Merge

No live runtime proof is authorized. Before merge, run every repository CI gate. After human merge, use a fresh isolated checkout and run the certified-source CLI against the exact local source-authority root and committed source manifest. Run LONG and SHORT discovery separately, preserve hashes, and leave the locked holdout untouched until a single frozen candidate is explicitly approved for one evaluation.

## What This PR Does Not Prove

This work does not prove structural edge, option profitability, executable Profit Factor, realistic fills, slippage tolerance, strict option WFA success, locked-holdout success, paper readiness, live readiness, or production strategy correctness. Any survivor must be ported independently to the strict option replay engine with real strike-selection and bid/ask path provenance.

## Human Approval

Human approval is required for merge, local corpus execution, candidate selection, locked-holdout evaluation, strict option-replay integration, shadow integration, and every production or live decision. This PR must remain draft and must not be auto-merged.
