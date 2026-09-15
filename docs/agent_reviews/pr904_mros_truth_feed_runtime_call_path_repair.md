# PR 904 — MROS Truth Feed Runtime Call Path Repair & Authority Alignment

## Evidence Contract Fields

- mode: PAPER
- candidate_id: pr904-mros-truth-feed-runtime-call-path-repair
- decision: REVIEW_ONLY
- reason: Align MROS Truth Feed runtime call path with canonical scoring, ranking, and TradeBuilder authority; eliminate false positive unreachable stage blockers.
- timestamp: 2026-09-15T08:50:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/pr904_mros_truth_feed_runtime_call_path_repair.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: #904
- Branch: fix/mros-scoring-ranking-trade-builder-repair
- Scope:
  - Upgrade `MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json` to V4 with explicit stage classifications (17 `CAUSAL`, 2 `OBSERVABILITY_SIDECAR`, 1 `EXECUTION_BOUNDARY`).
  - Correct callers/callees for SCORING, RANKING, and TRADE_BUILDER to point to canonical runtime authorities (`core.ranking_orchestrator`, `core.opportunity_scoring`, `core.candidate_ranking`, `strategies.trade_builder.TradeBuilder`).
  - Add independent verifier `scripts/verify_mros_runtime_call_path.py` and pre-merge proof ledger `/Volumes/TradeBotData/pr904-runtime-proof-20260915/MROS_RUNTIME_CALL_LEDGER.json`.
  - Update `core/mros_daily_governor.py` to evaluate causal reachability without false-blocking on sidecars.
  - Update `tests/test_trade_truth_prospective_repair.py` to eliminate fake self-certified boolean assertions and add dynamic verifier and mutation tests.
- Allowed files:
  - MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json
  - scripts/verify_mros_runtime_call_path.py
  - core/mros_daily_governor.py
  - tests/test_trade_truth_prospective_repair.py
  - docs/agent_reviews/pr904_mros_truth_feed_runtime_call_path_repair.md
- Forbidden files:
  - core/broker/*
  - core/order*
  - core/execution*
  - config/*
  - run_live.sh
  - TRADE_TRUTH_PROSPECTIVE_FULL_CAPTURES.json
- Forbidden behaviors:
  - No broker write calls or order actions.
  - No live trading authority enabled.
  - No alternative or competing candidate selection engine (`select_best_opportunity` remains sole authority).
  - No modification to historical frozen evidence captures.
- Acceptance tests:
  - 25/25 tests in tests/test_trade_truth_prospective_repair.py pass.
  - scripts/verify_mros_runtime_call_path.py passes on dynamic proof ledger.
  - validate_agent_review_evidence.py passes.
  - CE gates (Minerva, Cerberus, Evidence) pass.
- Pre-merge runtime proof required:
  - Dynamic execution proof ledger generated at `/Volumes/TradeBotData/pr904-runtime-proof-20260915/MROS_RUNTIME_CALL_LEDGER.json` with `PRE_MERGE_RUNTIME_PROOF_REQUIRED=true`.

## Scope Guard

Verdict: PASS

Checked:

- [x] No broker write endpoints called (`broker_api_called=false`).
- [x] No live order actions (`is_order_action=false`, `ORDERS_PLACED=0`, `ORDERS_MODIFIED=0`, `ORDERS_CANCELLED=0`).
- [x] No credentials or secrets modified.
- [x] Single candidate selection authority strictly preserved (`core.opportunity_engine.select_best_opportunity`).
- [x] Read-only observability/UI classification preserved for scoring and ranking.
- [x] Zero changes to frozen historical evidence captures.

Blocking issues: none.

## High-Risk Path Review

Verdict: NOT APPLICABLE

No forbidden high-risk runtime execution paths (such as core/execution_engine.py, core/auth.py, config/) are modified. The changes are strictly confined to the truth feed call path contract, associated tests, and agent review documentation.

## Grill Me Review

Verdict: PASS

Questions asked and verified:

1. Does marking SCORING, RANKING, and TRADE_BUILDER as reachable introduce a dual decision path?
   - No. `core/runtime_authority_contract.py` confirms `score_opportunities` and `rank_candidates` have authority `UI_ONLY` (read-only audit/observability), while `select_best_opportunity` is the sole candidate selection authority. `TradeBuilder` is the canonical candidate constructor.
2. Does this PR weaken any negative controls in tests?
   - No. Test `test_unproven_production_stages_blocked_not_fabricated` remains active and tests against frozen captures. Broker write guard fail-closed tests continue to pass.
3. Does this change bypass any risk or broker checks?
   - No. Zero broker calls, zero order authority.

## Hermes Review

Verdict: PASS

Architecture review:

- Call path contract updated from V2 to V3 to accurately reflect existing production runtime architecture.
- Downstream stages SCORING and RANKING correctly reference `core.ranking_orchestrator.build_ranked_opportunity_report` which executes in `produce_and_store_runtime_snapshots` during read-only observation cycles.
- TRADE_BUILDER correctly references `strategies.trade_builder.TradeBuilder`.

## GSD Review

Verdict: PASS

Execution summary:

- Upgraded `MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json` to V4 with stage classifications (17 CAUSAL, 2 OBSERVABILITY_SIDECAR, 1 EXECUTION_BOUNDARY).
- Created independent runtime verifier `scripts/verify_mros_runtime_call_path.py`.
- Updated `core/mros_daily_governor.py` to evaluate causal reachability without false-blocking on sidecars.
- Updated `tests/test_trade_truth_prospective_repair.py` replacing self-certified boolean assertions with instrumented dynamic counters and negative mutation tests.
- Generated dynamic pre-merge runtime proof ledger at `/Volumes/TradeBotData/pr904-runtime-proof-20260915/MROS_RUNTIME_CALL_LEDGER.json`.

## QA / Safety Review

Verdict: PASS

Safety properties verified:

- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_authorized=false`
- `ORDERS_PLACED=0`
- `ORDERS_MODIFIED=0`
- `ORDERS_CANCELLED=0`
- `observed_broker_writes=0`

## Acceptance Proof

Commands executed:

```bash
python3 -m pytest -q tests/test_trade_truth_prospective_repair.py
python3 scripts/verify_mros_runtime_call_path.py
python3 scripts/validate_agent_review_evidence.py --base-ref origin/main --candidate-ref HEAD
PYTHONPATH=. python3 scripts/run_unified_ce_gates.py --repo . --config .gsd-forensics.yaml --changed-paths-file docs/code_excellence/reports/changed_paths.txt
```

Results:

- 25/25 tests in `tests/test_trade_truth_prospective_repair.py` passed.
- `scripts/verify_mros_runtime_call_path.py` verified 20 stages, 17 causal stages, 1 candidate selection authority, 0 broker writes.
- `validate_agent_review_evidence.py` passed.
- Unified CE gates passed.

## Pre-Merge Runtime Proof Artifact

- Ledger path: `/Volumes/TradeBotData/pr904-runtime-proof-20260915/MROS_RUNTIME_CALL_LEDGER.json`
- Independent verifier: `scripts/verify_mros_runtime_call_path.py`
- Pre-merge runtime proof status: `PRE_MERGE_RUNTIME_PROOF_REQUIRED=true` (SATISFIED)
- Verification result: 20 stages verified, 17 causal stages, 1 candidate selection authority, 0 broker writes.

## What This PR Does Not Prove

1. It does not certify Full Causal Level-C live execution (strictly `FULL_CAUSAL_LEVEL_C=NOT_CERTIFIED`).
2. It does not record prospective live decisions before live market ticks arrive (`PROSPECTIVE_LIVE_DECISIONS=0`).
3. It does not evaluate strategy profitability or market predictability.
4. It does not grant order placement authority.

## Human Approval

Human approval required for final merge into canonical main.
