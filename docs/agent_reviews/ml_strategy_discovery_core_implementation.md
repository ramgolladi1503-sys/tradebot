# ML Strategy Discovery Core — Agent Review Evidence

- mode: ML_STRATEGY_DISCOVERY_CORE_V2
- candidate_id: ML_DISCOVERY_CORE_AND_CERTIFIED_SOURCE_ADAPTER
- decision: IMPLEMENTED_PENDING_CURRENT_HEAD_CI_AND_REAL_CORPUS_RUN
- reason: The causal discovery core is implemented and now binds certified source files with explicit start-labelled bar semantics; current-head CI and the actual local corpus run remain required before accepting generated candidates.
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
- scope: Implement causal completed-bar discovery, interpretable model and rule extraction, frozen-rule validation controls, explicit timestamp authority, and a manifest-bound underlying-data adapter.
- requested_paths: `research/ml_strategy_discovery/`, `scripts/run_ml_strategy_discovery.py`, `tests/test_ml_strategy_discovery_*.py`, and ML-discovery evidence documentation.
- allowed_paths: only the requested research, CLI, focused tests, and evidence paths.
- forbidden_paths: production runtime, `main.py`, `run_live.sh`, `config/`, credentials, broker, execution, order, risk, feed, dashboard, production strategies, `.env`, secrets, live runtime, and source parquet mutation.
- expected_tests: focused ML-discovery tests, source-adapter negative tests, compile check, full repository tests, health gate, CodeQL, Code Excellence, repo-forensics, evidence gate, registry verification, and gitleaks.
- acceptance_proof: start-labelled bars are available only at bar end; certified files are contained, hashed, reopened, and session-verified; development-only model fitting is isolated from holdout; extracted rules reproduce their source tree leaves with frozen imputation; underlying label metrics are not called option P&L.

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

The dangerous assumption in the original core was that a source timestamp represented a completed decision timestamp. The certified Upstox corpus uses start-labelled one-minute bars. Using the row's close, high, low, or volume at the start timestamp would leak the entire candle. The v2 contract now represents bar start and bar end separately and uses bar end as the decision, feature cutoff, and source-data maximum timestamp.

A second fake-confidence risk was rule extraction after median imputation. A tree can route a missing feature using its development-fitted median, while a later human-readable rule evaluator may treat the same missing value as false. The frozen candidate now carries the development imputation values for every path feature and is rejected if its deterministic mask does not exactly reproduce the source leaf on development rows.

The current label return remains an underlying ATR research label. It is not an executable entry, fill, option premium return, or transaction-cost result. Metrics are therefore explicitly named `label_profit_factor`, `label_expectancy_r`, and related label terms.

## Hermes Review

The architecture has separate owners:

1. Source adapter: selects only certified manifest records and independently verifies contained files.
2. Dataset contract: converts source timestamps into explicit completed-bar decision timestamps.
3. Feature and label construction: uses completed bars and same-session future paths.
4. Development-only discovery models: fit imputer, shallow tree, and XGBoost comparison without fitting or scoring on locked holdout.
5. Candidate contract: freezes side, thresholds, leaf ID, source-development dataset hash, and imputation values.
6. Independent evaluator and oracle: reproduce rule masks and evaluate only declared temporal scopes.
7. Strict option replay: remains outside this package as a later independent validation authority.

No production inference, ranking, risk, broker, dashboard, or execution owner imports the discovery package.

## GSD Review

Implemented components:

- START and END timestamp semantics
- source timezone and bar interval contract
- bar-start and bar-end metadata
- strict one-minute cadence option
- finite and ordered OHLCV validation
- certified Upstox source-manifest adapter
- path containment and symlink rejection
- source SHA-256, byte-size, row-count, schema, symbol, session, and cadence checks
- row and session conservation
- causal market-structure and event features
- same-session LONG and SHORT triple-barrier labels
- chronological whole-session development, validation, and locked holdout partitions
- shallow decision tree plus deterministic CPU XGBoost comparison
- frozen candidate leaf ID, side, development dataset hash, and imputation values
- exact candidate-mask versus source-tree-leaf reproduction gate
- label permutation, timestamp shift, ablation, parameter, and abstract label-cost controls
- independent future-mutation and rule-mask oracles
- research CLI supporting certified corpus or explicit file input
- evidence and source-adapter manifests with non-action safety fields

## QA / Safety Review

The earlier branch head passed both full repository test workflows, health gates, CodeQL, registry verification, Portfolio CI, and repo-forensics, but failed the evidence and Code Excellence gates because the evidence files did not satisfy required repository contracts.

The v2 repair adds the exact evidence fields and literal non-action flags required by those gates. Current-head validation is not yet claimed in this document. It must be established by GitHub CI after these changes and by a local actual-corpus run from the source-authority checkout.

Focused tests now cover:

- START timestamp to bar-end decision conversion
- equivalent END-labelled interval conversion
- strict cadence failure
- deterministic dataset hashes
- duplicate timestamp failure
- future mutation changes labels but not features
- whole-session split isolation
- holdout mutation cannot change development or validation artifacts
- frozen imputation behavior
- exact tree-leaf reproduction
- same-bar ambiguity
- same-session horizon enforcement
- SHORT direction correctness
- certified source file reopen and row conservation
- SHA mismatch rejection
- path escape rejection before data use
- incomplete-session rejection

## Acceptance Proof

- start-labelled bar high, low, close, and volume available at source timestamp: REJECTED
- completed decision time for one-minute start-labelled bar: SOURCE TIMESTAMP PLUS ONE MINUTE
- explicit file with missing timestamp semantics: FAIL CLOSED
- irregular certified session cadence: FAIL CLOSED
- source path outside certified root: FAIL CLOSED
- source symlink component: FAIL CLOSED
- source SHA mismatch: FAIL CLOSED
- source incomplete session: FAIL CLOSED
- source symbol or session mismatch: FAIL CLOSED
- future mutation changes current features: FAIL CLOSED BY TEST
- same-bar target and stop: AMBIGUOUS AND CONSERVATIVELY LABELLED AS STOP
- next-session gap satisfies intraday label: PROHIBITED
- model imputer fitted outside development: PROHIBITED
- candidate missing development imputation values: CANNOT REPRODUCE SOURCE LEAF
- extracted candidate differs from source tree leaf: FAIL CLOSED
- holdout fitted or validation-scored by discovery model: PROHIBITED
- option profitability inferred from underlying labels: PROHIBITED
- live candidate status: ABSENT

## Runtime Proof Required After Merge

No live runtime proof is authorized. Before any merge decision, run the current branch through all repository CI gates. After human merge, use a fresh isolated checkout and invoke the certified-source CLI against the exact local source-authority root and committed source manifest. Run LONG and SHORT discovery separately. Preserve output hashes and do not evaluate the locked holdout until a single candidate is frozen and explicitly approved for one-time holdout consumption.

## What This PR Does Not Prove

This work does not prove structural edge, option profitability, executable Profit Factor, realistic fills, slippage tolerance, strict option WFA success, locked-holdout success, paper readiness, live readiness, or production strategy correctness. A positive underlying label result cannot be promoted until the frozen rule is independently ported to the strict option replay engine with real strike-selection and bid/ask path provenance.

## Human Approval

Human approval is required for merge, actual-corpus execution that consumes substantial local data, candidate selection, any locked-holdout evaluation, strict option-replay integration, shadow integration, and every production or live decision. This PR must remain draft and must not be auto-merged.
