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
  - Quarantined previous synthetic stage loop ledger under `/Volumes/TradeBotData/pr904-runtime-proof-20260915/invalidated/` with `INVALIDATED_RUNTIME_PROOF_RCA.json`.
  - Generated real canonical observation proof artifacts under `/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/`.
  - Audited canonical read-only observation runtime: identified that `TRADE_BUILDER` is not reached in canonical observer, correctly classifying it as `BLOCKED_RUNTIME_INTEGRATION` without fabricated claims.
  - Implemented decoupled independent verifier `scripts/verify_mros_runtime_call_path.py` asserting reachability, provenance, checkpoint continuity, single selection authority, and zero broker calls.
  - Updated `core/mros_daily_governor.py` and `tests/test_trade_truth_prospective_repair.py` with comprehensive mutation, origin rejection, and fail-closed tests.
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
  - 30/30 tests in tests/test_trade_truth_prospective_repair.py pass.
  - scripts/verify_mros_runtime_call_path.py passes on real proof ledger.
  - validate_agent_review_evidence.py passes.
  - CE gates (Minerva, Cerberus, Evidence) pass.
- Pre-merge runtime proof:
  - Artifacts generated at `/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/` with `PRE_MERGE_RUNTIME_PROOF_REQUIRED=true`.

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

No forbidden high-risk runtime execution paths (such as core/execution_engine.py, core/auth.py, config/) are modified. Downstream stage validation in core/mros_daily_governor.py strictly classifies stages without altering order/execution authority.

## Grill Me Review

Verdict: PASS

Questions asked and verified:

1. Was the synthetic proof loop invalidated?
   - Yes. The previous synthetic ledger was quarantined under `/Volumes/TradeBotData/pr904-runtime-proof-20260915/invalidated/` with `INVALIDATED_RUNTIME_PROOF_RCA.json`.
2. How is TRADE_BUILDER proven in runtime?
   - Causal audit revealed `strategies.trade_builder.TradeBuilder` is not called by the canonical read-only observation runtime. It is honestly marked `runtime_reachable=false` (`BLOCKED_RUNTIME_INTEGRATION`). It is NOT fabricated.
3. How is zero broker write verified?
   - `observed_broker_calls = sum(CALL_COUNTS.values())` dynamically verified as 0 before and after canonical execution attempts.

## Hermes Review

Verdict: PASS

Architecture review:

- Call path contract updated to V4 reflecting stage classifications: 17 CAUSAL, 2 OBSERVABILITY_SIDECAR, 1 EXECUTION_BOUNDARY.
- Real canonical runtime origin (`CANONICAL_RUNTIME_OBSERVATION`) enforced; synthetic and manual loop claims rejected by independent verifier.
- TradeBuilder integration cleanly blocked until genuine runtime connection is merged.

## GSD Review

Verdict: PASS

Execution summary:

- Upgraded `MROS_TRUTH_FEED_RUNTIME_CALL_PATH.json` to V4.
- Quarantined synthetic proof with RCA.
- Generated real canonical observation artifacts under `/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/`.
- Created independent runtime verifier `scripts/verify_mros_runtime_call_path.py`.
- Updated `core/mros_daily_governor.py` and `tests/test_trade_truth_prospective_repair.py`.

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

- 30/30 tests in `tests/test_trade_truth_prospective_repair.py` passed.
- `scripts/verify_mros_runtime_call_path.py` verified 20 stages, 17 causal stages (1 blocked), 1 candidate selection authority, 0 broker writes.
- `validate_agent_review_evidence.py` passed.
- Unified CE gates passed.

## Pre-Merge Runtime Proof Artifacts

- Directory: `/Volumes/TradeBotData/pr904-runtime-proof-20260915-real/`
- Required artifacts:
  - `MROS_CANONICAL_RUNTIME_OBSERVED_CALLS.json`
  - `MROS_CANONICAL_TRUTH_CHECKPOINTS.json`
  - `MROS_RUNTIME_CALL_LEDGER.json`
  - `MROS_RUNTIME_PROOF_VERIFICATION.json`
  - `BROKER_WRITE_AUDIT.json`
- Independent verifier: `scripts/verify_mros_runtime_call_path.py`
- Pre-merge runtime proof status: `PRE_MERGE_RUNTIME_PROOF_REQUIRED=true` (SATISFIED)

## Runtime Proof Required After Merge

Required after merge:

1. Run `python scripts/morning_readiness_cli.py governor --session-date 2026-09-15` to verify morning readiness evaluates downstream capture states fail-closed against verified runtime proof.
2. Complete canonical runtime wiring for `TRADE_BUILDER` in a dedicated, approved PR before live execution can be unblocked.

## What This PR Does Not Prove

1. It does not certify Full Causal Level-C live execution (strictly `FULL_CAUSAL_LEVEL_C=NOT_CERTIFIED`).
2. It does not claim `TRADE_BUILDER` is reachable in the canonical read-only observation runtime (`TRADE_BUILDER_RUNTIME_STATE=BLOCKED_RUNTIME_INTEGRATION`).
3. It does not record prospective live decisions before live market ticks arrive (`PROSPECTIVE_LIVE_DECISIONS=0`).
4. It does not evaluate strategy profitability or market predictability.
5. It does not grant order placement authority.

## Human Approval

Human approval required for final merge into canonical main.
