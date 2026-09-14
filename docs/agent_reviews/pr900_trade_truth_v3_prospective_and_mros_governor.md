# PR 900 — Trade Truth V3 Prospective Capture Ready & MROS Daily Governor

## Evidence Contract Fields

- mode: PAPER
- candidate_id: pr900-trade-truth-v3-prospective-mros-governor
- decision: REVIEW_ONLY
- reason: Trade Truth V3 prospective Level-C causal capture ready and fail-closed MROS daily morning governor resolution.
- timestamp: 2026-09-15T00:00:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/pr900_trade_truth_v3_prospective_and_mros_governor.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: #900
- Branch: feature/trade-truth-v3-prospective-full-c
- Scope:
  - Trade Truth V3 prospective Level-C causal capture engine and replay infrastructure.
  - Fail-closed MROS daily governor resolving session date, ReleaseStore pointer, 10 GiB storage threshold, Tuesday weekly NIFTY expiry, and canonical C1/C2 strategy catalog.
  - Integration of TruthFeedRuntimeHook into morning preflight path.
- Allowed files:
  - core/trade_truth/*
  - core/candidate_journal.py
  - core/mros_daily_governor.py
  - scripts/morning_readiness_cli.py
  - scripts/run_trade_truth_*
  - scripts/verify_trade_truth_*
  - tests/trade_truth/*
  - tests/test_trade_truth_prospective_repair.py
  - docs/agent_reviews/pr900_trade_truth_v3_prospective_and_mros_governor.md
- Forbidden files:
  - core/broker/*
  - core/order*
  - core/execution*
  - config/*
  - run_live.sh
- Forbidden behaviors:
  - No broker write calls or order actions.
  - No live trading authority enabled.
  - No synthetic market records labeled as live prospective observations.
- Acceptance tests:
  - 18/18 tests in tests/test_trade_truth_prospective_repair.py pass.
  - 63/63 tests in tests/trade_truth/ pass.
  - Independent prospective level C verifier passes.
  - validate_agent_review_evidence.py passes.
- Runtime proof required:
  - Pre-market readiness evaluation for 2026-09-15 correctly fails closed if kite access token is missing or unverified.

## Scope Guard

Verdict: PASS

Checked:

- [x] No broker write endpoints called (`broker_api_called=false`).
- [x] No live order actions (`is_order_action=false`, `ORDERS_PLACED=0`, `ORDERS_MODIFIED=0`, `ORDERS_CANCELLED=0`).
- [x] No credentials or secrets modified.
- [x] Storage threshold strictly set to 10 GiB.
- [x] Weekly NIFTY expiry strictly Tuesday.
- [x] Governed strategy catalog deduplicated to canonical C1 and C2 ACTIVE_APPROVED logical families.

Blocking issues: none.

## High-Risk Path Review

Verdict: NOT APPLICABLE

No forbidden high-risk runtime execution paths (such as core/execution_engine.py, core/auth.py, config/) are modified. The changes are strictly confined to observation, truth feed instrumentation, and morning preflight governance.

## Grill Me Review

Verdict: PASS

Questions asked and verified:

1. Does the governor fail open if the release store is absent or mismatched?
   - No, it fails closed to `BLOCKED_RELEASE` with explicit blockers.
2. Does it use the correct weekly expiry for NIFTY contracts?
   - Yes, Tuesday weekly expiry is enforced; Thursday expiry for weekly NIFTY contracts is hard-rejected.
3. Are offline replay decisions separated from live prospective observations?
   - Yes, strictly enforced (`offline_replay_decisions > 0`, `prospective_live_decisions == 0`).

## Hermes Review

Verdict: PASS

Architecture review:

- Dedicated `MROSDailyGovernor` centralizes pre-market resolution without operator guesswork.
- Uses canonical `ReleaseStore` and `create_session_root` contracts.
- Isolated preflight writer self-test avoids polluting the causal session truth store.

## GSD Review

Verdict: PASS

Execution summary:

- Repaired all material governor defects.
- Extended `scripts/morning_readiness_cli.py` with `governor` subcommand.
- Added comprehensive unit and regression tests for Tuesday expiry, release store fail-closed, clean tree gate, and 10 GiB storage threshold.

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

## Acceptance Proof

Commands executed:

```bash
python3 -m pytest -q tests/test_trade_truth_prospective_repair.py tests/trade_truth/
python3 scripts/verify_trade_truth_prospective_level_c.py
python3 scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Results:

- 18/18 tests in `tests/test_trade_truth_prospective_repair.py` passed.
- 63/63 tests in `tests/trade_truth/` passed.
- Verifier reported `PASS`.
- `validate_agent_review_evidence.py` passed.

## Runtime Proof Required After Merge

Required after merge:

1. Promote the merged SHA in the operational `ReleaseStore`.
2. Run `python scripts/morning_readiness_cli.py governor --session-date 2026-09-15` to verify `CURRENT_RUNTIME_SHA == CERTIFIED_RELEASE_SHA == MERGED_MAIN_SHA`.
3. Provision read-only Kite access token and confirm read-only observation readiness.

## What This PR Does Not Prove

1. It does not certify Full Causal Level-C live execution (strictly `FULL_CAUSAL_LEVEL_C=NOT_CERTIFIED`).
2. It does not record prospective live decisions before live market ticks arrive (`PROSPECTIVE_LIVE_DECISIONS=0`).
3. It does not evaluate strategy profitability or market predictability.
4. It does not grant order placement authority.

## Human Approval

Human approval required for final merge into canonical main and operational ReleaseStore promotion.
