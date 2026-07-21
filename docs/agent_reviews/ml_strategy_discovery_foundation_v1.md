# ML Strategy Discovery Foundation v1 Agent Review

- mode: ML_STRATEGY_DISCOVERY_FOUNDATION_V1
- decision: FOUNDATION_IMPLEMENTED_DATA_INTEGRATION_PENDING
- claim_boundary: NO_EDGE_OR_PROFITABILITY_CLAIM
- read_only: true
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- source_agent: ChatGPT
- action: GENERATE_PATCH
- title: ML strategy discovery foundation v1
- scope: Implement data-independent contracts, causal labels, chronological validation, interpretable models, rule extraction, negative controls, a research-only candidate registry, and independent audits.
- requested_paths: `research/ml_strategy_discovery/`, `scripts/audit_ml_strategy_discovery_foundation.py`, `tests/test_ml_strategy_discovery_*.py`, `docs/research/ml_strategy_discovery_foundation_v1.md`, and this review.
- allowed_paths: exactly the requested research, audit-script, focused-test, and evidence paths.
- forbidden_paths: `main.py`, `run_live.sh`, `config/`, `credentials.py`, `core/execution*`, `core/broker*`, `core/order*`, `core/risk*`, `core/feed*`, `strategies/`, `dashboard/`, `runtime/live*`, `.env`, `*.env`, and `secrets*`.
- expected_tests: focused deterministic pytest suite, standalone contract audit, compile check, forbidden-import scan, and repository CI.
- acceptance_proof: causal availability checks fail closed; labels use strictly future bars; partitions are chronological and disjoint; WFA has an explicit purge gap; registry has no LIVE state; locked-holdout consumption fails audit.

## Scope Guard

- PRODUCTION FILES TOUCHED: NONE
- STRATEGY FILES TOUCHED: NONE
- RUNTIME WIRING: NONE
- BROKER ADAPTERS TOUCHED: NONE
- RISK OR FEED GATES TOUCHED: NONE
- DASHBOARD FILES TOUCHED: NONE
- CREDENTIAL OR ENVIRONMENT FILES TOUCHED: NONE
- ORDER ACTIONS: NONE
- BROKER API CALLED: NO
- LIVE EXECUTION ENABLED: NO

## Grill Me Review

The main failure mode is not missing model sophistication; it is fake discovery caused by timestamp leakage, random time-series splitting, holdout reuse, opaque rules, or optimistic same-bar path resolution. The implementation attacks those failure modes directly. It does not pretend that a scaffold without bound market data has discovered a strategy.

Two deliberate limitations are truthful rather than incomplete-by-accident: no TradeBot dataset adapter is guessed, and no Profit Factor or edge result is generated from synthetic data. Those remain blocked until authoritative underlying and options sources are inventoried, hashed, and aligned.

## Hermes Review

The architecture separates discovery from evaluation. Causal observations and path-dependent labels feed offline models; shallow-tree rules can be extracted into explicit conditions; candidate dossiers remain research/shadow-only; independent audits enforce chronology, disjoint partitions, and locked-holdout non-consumption. No package module imports runtime, broker, order, risk, feed, dashboard, or production strategy code.

## GSD Review

Implementation stayed inside the declared research-only scope. Added causal contracts, triple-barrier labels, deterministic matrix assembly, chronological partitions, purged anchored WFA, deterministic negative controls, shallow-tree and XGBoost adapters, readable rule extraction, a no-LIVE candidate registry, independent audits, focused tests, a standalone audit script, and documentation. Existing production files were not modified.

## QA / Safety Review

- Focused local suite: `20 passed`.
- `python scripts/audit_ml_strategy_discovery_foundation.py`: returned `FOUNDATION_IMPLEMENTED_DATA_INTEGRATION_PENDING` and `NO_EDGE_OR_PROFITABILITY_CLAIM`.
- `python -m compileall -q research/ml_strategy_discovery scripts/audit_ml_strategy_discovery_foundation.py`: passed.
- Forbidden-import scan for broker, execution, order, risk, feed, strategies, dashboard, Kite, and Upstox dependencies: no matches.
- Remote diff before this evidence repair: branch ahead of main, behind by zero, added files only, no deletions.
- Repository CI: must pass before merge; local focused tests do not replace CI.

## Acceptance Proof

- future feature availability violations: FAIL CLOSED
- naive timestamps: FAIL CLOSED
- non-finite features: FAIL CLOSED
- strictly future legal entry bar: PROVED
- LONG and SHORT path labels: PROVED
- same-bar target and stop: CONSERVATIVE_STOP_FIRST with ambiguity retained
- deterministic feature ordering and observation ordering: PROVED
- inconsistent feature schemas: FAIL CLOSED
- chronological development/validation/holdout: PROVED
- partition overlap: FAIL CLOSED
- explicit WFA purge gap: PROVED
- deterministic label permutation: PROVED
- deterministic randomized entry offsets: PROVED
- interpretable tree depth cap: PROVED
- readable positive-leaf rule extraction: PROVED
- candidate registry LIVE status: ABSENT
- candidate status transition evidence hash: REQUIRED
- locked holdout consumed during discovery: FAIL CLOSED
- read_only: true
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Runtime Proof Required After Merge

No live runtime proof is authorized or required for this research-only foundation. After human merge, rerun the focused tests, standalone audit, and full repository CI from exact merged `origin/main`. The next data-bound phase must run in an isolated worktree and first prove dataset hashes, timestamp semantics, row conservation, deterministic adaptation, and holdout isolation before model fitting.

## What This PR Does Not Prove

This PR does not prove a structural edge, profitability, Profit Factor, Sharpe, drawdown quality, option executability, fill realism, slippage tolerance, WFA success, locked-holdout success, paper readiness, live readiness, or production strategy correctness. It does not train an authoritative model or discover a deployable strategy. It proves only that the offline discovery foundation exists with explicit causal, interpretability, validation, and safety contracts.

## Human Approval

Human approval is required for merge, authoritative dataset selection, any future candidate promotion, any shadow integration, and every production or live-execution decision. This PR must remain draft until repository CI passes and must not be auto-merged.
