# AGENT-ELITE-13 — Vulcan Production Hardening Score

mode: REVIEW
candidate_id: AGENT-ELITE-13-VULCAN-HARDENING-SCORE
decision: review_pending
reason: vulcan_static_hardening_score
source: docs/agent_reviews/AGENT_ELITE_13_VULCAN_HARDENING_SCORE.md
timestamp: 2026-05-28T20:10:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #385
Parent: #372
Depends on: #384 / PR #400 / merge commit 635c5a2d9bf434537c1c650ea1eea1551870651d

## Agent Work Contract

This PR implements AGENT-ELITE-13 only.

The work adds a static Vulcan hardening score for changed-file patches so production-grade claims become measurable.

It must not change production code, run product runtime code, call brokers, modify broker code, tune strategies, or change dashboard/UI behavior.

## Scope Guard

Allowed:

- Add `tools/code_excellence/vulcan/`.
- Add focused tests in `tests/test_vulcan_hardening_score.py`.
- Add this agent-review evidence file.

Not allowed:

- Production code changes.
- Runtime execution.
- Broker calls.
- Strategy tuning.
- Broker code changes.
- Dashboard/UI changes.
- External agent calls.
- Test skip/xfail in product tests.

## High-Risk Path Review

This PR adds isolated static code-excellence tooling only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

## Grill Me Review

Question: Does this execute product code?

Answer: No. It scores supplied static patch text and file metadata.

Question: Does this change production code?

Answer: No. It adds tooling and tests only.

Question: What happens when silent fallback appears?

Answer: The score is reduced and the reason is recorded.

Question: What happens when fail-closed behavior and negative tests appear?

Answer: The score increases and the reasons are recorded.

Question: What happens when runtime side-effect markers appear without scope?

Answer: The report blocks production-grade claims.

Question: What happens when score is below threshold?

Answer: Production-grade claim is not allowed.

## Hermes Review

The implementation is intentionally additive:

- Adds `HardeningInput`.
- Adds `HardeningScore`.
- Adds `score_hardening(...)`.
- Scores deterministic logic signals.
- Scores explicit failure handling.
- Scores safe defaults.
- Scores evidence-rich output.
- Scores negative tests.
- Penalizes silent fallback.
- Penalizes contract weakening risk.
- Blocks unscoped runtime side-effect markers.
- Blocks production-grade claim when threshold is not met.

## GSD Review

Smallest safe implementation:

- Keep Vulcan isolated under `tools/code_excellence/vulcan/`.
- No integration into CI gates yet.
- No repository mutation behavior.
- No runtime behavior.
- Deterministic pure scoring tests only.

Files changed:

- `tools/code_excellence/vulcan/__init__.py`
- `tools/code_excellence/vulcan/hardening_score.py`
- `tests/test_vulcan_hardening_score.py`
- `docs/agent_reviews/AGENT_ELITE_13_VULCAN_HARDENING_SCORE.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_vulcan_hardening_score.py -q
```

Safety assertions:

- No production code touched.
- No runtime import of target Tradebot modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard behavior change.
- Broker code is untouched.
- Strategy/ranking formulas are untouched.
- No code mutation path exists.

## Acceptance Proof

The tests prove:

- Silent fallback reduces score and records reason.
- Fail-closed behavior plus negative tests increases score.
- Unscoped runtime side-effect markers block production-grade claims.
- Score below threshold cannot claim production-grade.
- Contract weakening risk reduces score.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static code-excellence analysis only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not validate dynamic runtime dispatch.

## Human Approval

Required before merge.
