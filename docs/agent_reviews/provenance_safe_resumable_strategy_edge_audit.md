# Provenance-Safe Resumable Strategy Edge Audit

mode: PAPER_RESEARCH
candidate_id: provenance_safe_resumable_strategy_edge_audit
decision: tooling_only_safe_to_merge
reason: Adds offline provenance-safe dataset cataloging and resumable strategy edge audit tooling without broker, order, live, strategy, threshold, or feed behavior changes.
timestamp: 2026-06-30T01:00:46+05:30
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
read_only: true
source: docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md

## Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: Add provenance-safe resumable strategy edge audit

scope:
- Add offline dataset provenance classification for strategy edge audit inputs.
- Add duplicate dataset fingerprinting and canonical raw dataset selection.
- Add resumable fingerprint-based batch strategy proxy analysis.
- Separate data availability, proxy analysis, and executable option replay verdicts.
- Preserve offline-only behavior with no broker, order, live, strategy, threshold, feed, or risk-gate changes.

requested_paths:
- scripts/catalog_available_strategy_data.py
- scripts/analyze_all_available_strategy_edge.py
- tests/test_catalog_available_strategy_data.py
- tests/test_analyze_all_available_strategy_edge.py
- docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md

allowed_paths:
- scripts/catalog_available_strategy_data.py
- scripts/analyze_all_available_strategy_edge.py
- tests/test_catalog_available_strategy_data.py
- tests/test_analyze_all_available_strategy_edge.py
- docs/agent_reviews/provenance_safe_resumable_strategy_edge_audit.md

forbidden_paths:
- main.py
- run_live.sh
- config/
- credentials.py
- core/broker*
- core/execution*
- core/feed*
- core/order*
- core/risk*
- strategies/
- .env
- *.env
- runtime/live*
- logs/broker*
- secrets*

expected_tests:
- git diff --check
- python -m pytest -q tests/test_catalog_available_strategy_data.py tests/test_analyze_all_available_strategy_edge.py
- python -m py_compile scripts/catalog_available_strategy_data.py scripts/analyze_all_available_strategy_edge.py tests/test_catalog_available_strategy_data.py tests/test_analyze_all_available_strategy_edge.py
- python scripts/validate_agent_review_evidence.py --base-ref origin/main

acceptance_proof:
- read_only=true
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false
- no live Kite calls
- no order placement
- no runtime artifact commit required

## Scope Guard

In scope:
- Raw versus derived dataset classification.
- Raw market input eligibility flags and exclusion reasons.
- Dataset fingerprints, duplicate groups, canonical dataset paths, and duplicate filtering.
- Batch and resume behavior keyed by dataset fingerprint, not offset.
- Partial versus full proxy verdict separation.
- Explicit NOT_EXECUTABLE_OPTION_BACKTEST verdict when executable option replay data is absent.
- Tests proving derived reports are not raw edge input, duplicates are deduped, capped analysis is partial, and broker/order calls are not made.

Out of scope:
- Live trading behavior.
- Strategy logic.
- Strategy thresholds.
- Broker adapters.
- Order placement or cancellation.
- Feed freshness gates.
- Risk gates or kill switches.
- Runtime evidence artifacts.
- Any claim of proven strategy edge or executable option profit and loss.

## Grill Me Review

Primary false-positive risks:
- Derived backtest outputs could be mistaken for raw market evidence.
- Duplicate datasets could be counted multiple times and inflate confidence.
- A capped batch could be misread as full coverage.
- Index OHLC proxy results could be misread as executable option PnL.
- Resume logic could double-count or skip datasets if based only on position.

Mitigations:
- evidence_origin, eligible_as_raw_market_input, and exclusion_reason make provenance explicit.
- dataset_fingerprint, duplicate_group_id, is_duplicate, and canonical_dataset_path identify canonical raw inputs.
- selection_strategy, proxy_datasets_available, proxy_datasets_analyzed, proxy_datasets_skipped_due_to_cap, selected_dataset_paths, and skipped_dataset_paths expose partial coverage.
- data_availability_verdict, proxy_analysis_verdict, and executable_option_replay_verdict prevent one verdict from implying another.
- Resume uses processed dataset fingerprints, not a fake offset.

Residual risk:
- Directional proxy analysis remains a proxy and cannot prove executable option edge.
- Full evidence quality still depends on the actual raw datasets available after merge.
- Reports can still be misused by a human if the NOT_EXECUTABLE_OPTION_BACKTEST verdict is ignored.

## Hermes Review

Architecture:
- The cataloger inventories candidate files, classifies provenance, assigns raw input eligibility, and computes dataset fingerprints.
- The analyzer consumes the catalog, filters to eligible canonical raw datasets, applies explicit selection strategy and optional batch limits, and records processed dataset fingerprints for resumable progress.
- Output reports separate dataset availability from directional proxy analysis from executable option replay capability.
- The design is appendable offline evidence tooling. It does not wire into live execution or strategy selection.

Design constraints preserved:
- No global live state.
- No broker API dependency.
- No order adapter dependency.
- No strategy threshold mutation.
- No hidden fallback that upgrades missing data into executable evidence.

## GSD Review

Implemented tooling:
- scripts/catalog_available_strategy_data.py catalogs raw versus derived evidence, eligibility, duplicate fingerprints, duplicate groups, and canonical dataset paths.
- scripts/analyze_all_available_strategy_edge.py runs offline strategy proxy analysis only over eligible canonical raw datasets, supports batch/resume controls, and emits conservative verdicts.

Implemented tests:
- tests/test_catalog_available_strategy_data.py covers provenance classification, raw eligibility, derived report exclusion, and duplicate dataset handling.
- tests/test_analyze_all_available_strategy_edge.py covers partial/full verdict behavior, selected/skipped dataset reporting, executable option replay blocking, no broker/order calls, and resume behavior.

No runtime artifacts are required for merge. Generated outputs under runtime/backtests remain evidence artifacts, not source changes.

## QA / Safety Review

Safety assertions:
- broker_api_called=false
- is_order_action=false
- allowed_for_live_execution=false
- read_only=true
- no broker imports are required to run the audit tooling
- no order placement path is invoked
- option replay verdict remains NOT_EXECUTABLE_OPTION_BACKTEST without executable option quote or fill datasets

Tests prove:
- Derived backtest outputs are not eligible raw market input.
- runtime/backtests reports are excluded from edge input.
- Duplicate datasets are deduped.
- max-proxy-datasets produces PARTIAL_PROXY_ANALYSIS.
- Uncapped all-dataset analysis reports FULL_PROXY_ANALYSIS only when every eligible dataset is analyzed.
- Selected and skipped dataset paths are reported.
- Zero executable option replay datasets keeps NOT_EXECUTABLE_OPTION_BACKTEST.
- Broker and order calls are not made.

## Acceptance Proof

Local validation performed before PR:

```bash
git diff --check
python -m pytest -q tests/test_catalog_available_strategy_data.py tests/test_analyze_all_available_strategy_edge.py
python -m py_compile scripts/catalog_available_strategy_data.py scripts/analyze_all_available_strategy_edge.py tests/test_catalog_available_strategy_data.py tests/test_analyze_all_available_strategy_edge.py
```

Expected agent evidence validation after this document is added:

```bash
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Acceptance requires CI green on the PR head and no unrelated dirty files in the merge diff.

## Runtime Proof Required After Merge

After merge, run full coverage from updated main:

```bash
python scripts/catalog_available_strategy_data.py \
  --roots data runtime logs artifacts reports \
  --out runtime/backtests/full_index_ohlc_strategy_proxy_audit
```

```bash
python scripts/analyze_all_available_strategy_edge.py \
  --catalog runtime/backtests/full_index_ohlc_strategy_proxy_audit/available_data_catalog.csv \
  --out runtime/backtests/full_index_ohlc_strategy_proxy_audit \
  --selection-strategy all \
  --only-dataset-type INDEX_OHLC \
  --batch-size 50 \
  --resume
```

Repeat the analyzer command until:

```text
proxy_datasets_analyzed == proxy_datasets_available
proxy_datasets_skipped_due_to_cap == 0
proxy_analysis_verdict = FULL_PROXY_ANALYSIS
```

Do not treat partial runs as edge proof.

## What This PR Does Not Prove

This PR does not prove:
- Strategy edge.
- Executable option PnL.
- Broker fill quality.
- Slippage-adjusted profitability.
- Live trade readiness.
- Ranking calibration.
- Feed stability.
- Phase-2 acceptance quality.
- Any strategy should be promoted or tuned.

Current truth:
- Tooling ready.
- Full directional evidence pending.
- Executable option evidence missing.

## Human Approval

Human approval is required before:
- Using audit output to tune strategy thresholds.
- Promoting any strategy to paper or live trading.
- Treating directional proxy returns as executable option PnL.
- Changing live, broker, order, feed, risk, or strategy behavior based on these reports.

This PR is acceptable only as offline evidence tooling.
