# PR #532 — Advanced Offline Score Delta Evidence Engine

mode: PAPER
candidate_id: pr532-advanced-score-delta-evidence
signal_id: pr532-advanced-score-delta-evidence
strategy_id: profile_score_delta_evidence
decision: REVIEW_ONLY
reason: offline_default_vs_profile_score_delta_evidence
timestamp: 2026-06-08T17:55:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr532-advanced-score-delta-evidence.md

## Agent Work Contract

This PR introduces an offline, read-only evidence engine that compares default opportunity scoring against explicitly profile-aware opportunity scoring.

It does not wire profile scores into runtime ranking, paper trading, live trading, broker paths, feed behavior, dashboard behavior, or strategy generation.

## What This PR Proves

This PR proves that, for a given candidate set and downgrade report, the system can emit deterministic evidence showing:

- default score
- profile score
- score delta
- default rank estimate
- profile rank estimate
- rank delta
- profile name
- per-component weighted score deltas
- promotion/demotion explanation
- unchanged safety status

## What This PR Does Not Prove

This PR does not prove trading edge.

It does not prove profile-aware sorting should be enabled.

It does not prove PAPER runtime should consume profile scores.

It does not change ranking behavior.

It does not place or prepare orders.

## How This Can Fail

This work is unsafe if:

- a safety-suppressed candidate becomes executable because profile score increased
- profile scoring changes eligibility or bucket status unexpectedly
- rank estimates are presented as runtime ranking changes
- component deltas are omitted, making score movement unexplainable
- the evidence engine accepts missing profiles and silently compares default vs default

## How We Know Runtime Behavior Did Not Change

The new module is standalone: `core/profile_score_delta_evidence.py`.

It calls existing scoring and ranking reports only for offline/shadow evidence.

No orchestrator, broker, execution, feed, dashboard, strategy, or runtime module is changed.

The report serializes broker/order/live flags as literal false.

## How This Moves Toward Measurable Edge

This PR creates the first audit layer that can show whether profile-aware scoring actually changes candidate quality in explainable ways.

It gives later PRs the evidence basis to decide whether profile-aware ranking should be tested in shadow or paper mode.

## Grill Me Review

The main risk is mistaking score movement for edge. The PR avoids this by calling the output an evidence report, not a promotion gate.

The second risk is unsafe score promotion. The tests include a high-regime candidate with fallback quote safety blockers and prove it remains suppressed.

The third risk is unexplained score movement. Every candidate-level record includes a component-level weighted delta breakdown and a human-readable promotion/demotion reason.

## Hermes Review

Changed files:

- `core/profile_score_delta_evidence.py`
- `tests/test_profile_score_delta_evidence.py`
- `docs/agent_reviews/pr532-advanced-score-delta-evidence.md`

No runtime modules are modified.

## GSD Review

This PR is advanced because it does not merely record metadata. It creates falsifiable evidence:

- Did scores move?
- Which component moved them?
- Did rank estimates change?
- Did safety status remain unchanged?
- Was profile scoring explicitly supplied?

## QA / Safety Review

Focused commands:

```bash
PYTHONPATH=. pytest tests/test_profile_score_delta_evidence.py
PYTHONPATH=. pytest tests/test_opportunity_scoring.py tests/test_opportunity_scoring_regime_profile_opt_in.py tests/test_candidate_ranking.py
```

Expected proof:

- score delta report is JSON serializable
- profile is mandatory
- score movement has component explanations
- rank estimate movement is shadow/evidence only
- unsafe candidates remain suppressed

## Acceptance Gates

- No broker calls.
- No order actions.
- No live order actions.
- No runtime wiring.
- No ranking cutover.
- No dashboard dependency.
- No candidate can be promoted without component delta evidence.
- No safety-suppressed candidate can become executable due to profile score.

## Human Approval

Human approval is required before merge.

Do not merge because the report looks useful. Merge only if it remains offline, read-only, and safety-preserving.
