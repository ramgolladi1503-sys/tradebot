# AGENT-ELITE-03 — Minerva Test Strength Scoring

mode: REVIEW
candidate_id: AGENT-ELITE-03-MINERVA-TEST-STRENGTH-SCORING
decision: review_pending
reason: minerva_static_test_strength_scoring
timestamp: 2026-05-28T13:45:00Z
source: docs/agent_reviews/AGENT_ELITE_03_MINERVA_TEST_STRENGTH.md
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #375
Parent: #372
Depends on: #374 / PR #390 / merge commit 0bff0259a69781e580c35d02dc3cb2fc0d831ce4

## Agent Work Contract

This PR implements AGENT-ELITE-03 only.

The work adds deterministic Minerva test-strength scoring beside the existing test-reality classification contract. It must not weaken existing class outputs, change trading runtime, call brokers, touch live behavior, change strategy logic, or modify dashboard behavior.

## Scope Guard

Allowed:

- Extend `tools/repo_forensics/test_reality.py` with score metadata.
- Extend `tests/test_repo_forensics_test_reality.py` with scoring coverage.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Live order behavior.
- Strategy/ranking behavior changes.
- Dashboard/UI changes.
- Broad repo-forensics refactor.
- Test skip/xfail.
- Weakening existing Minerva blocked classes.

## High-Risk Path Review

This PR touches static repo-forensics test analysis only.

High-risk Tradebot paths intentionally unchanged:

- `core/kite_client.py`
- `core/execution_engine.py`
- `core/execution_router.py`
- `core/risk_engine.py`
- `core/orchestrator.py`
- `strategies/`
- `dashboard/`
- `config/`

Minerva continues to classify files statically and does not import or execute target runtime modules.

## Grill Me Review

Question: Does this make weak tests pass as strong?

Answer: No. Existing classes remain unchanged. `FAKE_CONFIDENCE`, `SHAPE_ONLY`, and `UNKNOWN` remain weak/blocked by the current Minerva gate behavior.

Question: Could the score hide fake-confidence tests?

Answer: No. Fake-confidence markers subtract score and keep the grade weak.

Question: Does this prove every test is enterprise-grade?

Answer: No. It exposes strength scoring so weak tests become more visible.

Question: Does this touch trading behavior?

Answer: No. It is static test-file analysis only.

## Hermes Review

The contract is intentionally additive:

- Preserve `test_class`.
- Preserve `strength`.
- Add `strength_score`.
- Add `strength_grade`.
- Add `score_reasons`.
- Add report helpers for grade counts, weak tests, and strong tests.

## GSD Review

Smallest safe implementation:

- Add immutable `TestStrengthScore`.
- Add `score_test_strength(...)`.
- Route all statuses through a small `_status(...)` helper.
- Add scoring tests for weak, medium, strong, fake-confidence, and mock-only patterns.

Files changed:

- `tools/repo_forensics/test_reality.py`
- `tests/test_repo_forensics_test_reality.py`
- `docs/agent_reviews/AGENT_ELITE_03_MINERVA_TEST_STRENGTH.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_test_reality.py -q
```

Recommended additional command:

```bash
PYTHONPATH=. pytest tests/test_repo_forensics_test_reality.py tests/test_repo_forensics_candidate_trace.py -q
```

Safety assertions:

- No runtime import of target modules.
- No broker calls.
- No order behavior.
- No live execution.
- No dashboard changes.
- Existing blocked classes are not weakened.

## Acceptance Proof

The tests prove:

- Existing class classification remains intact.
- No-assertion tests remain UNKNOWN and weak.
- Strong safety tests receive strong score.
- Medium behavior tests receive medium score.
- Unknown tests remain weak.
- Fake-confidence scoring is penalized.
- Mock-only proof without negative coverage is penalized.

## Runtime Proof Required After Merge

No live runtime proof is required for this PR. This is static test-strength scoring only.

## What This PR Does Not Prove

- Does not prove live startup succeeds.
- Does not prove candidate quality.
- Does not prove ranking formula quality.
- Does not prove broker readiness.
- Does not prove profitability.
- Does not prove dashboard accuracy.
- Does not enforce the full critical negative test matrix; that belongs to AGENT-ELITE-04.

## Human Approval

Required before merge.
