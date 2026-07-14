# PR3 - Canonical Regime Score Separation

mode: PAPER
candidate_id: pr3-canonical-regime-score-separation
signal_id: pr3-canonical-regime-score-separation
strategy_id: canonical_regime_score_separation
decision: REVIEW_ONLY
reason: make_score_separation_and_edge_ranking_consume_shared_regime_truth_without_execution_changes
timestamp: 2026-06-15T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr3-canonical-regime-score-separation.md

## Agent Work Contract

This PR makes candidate scoring and edge ranking consume the shared regime canonicalizer added in PR2, while preserving the stronger analytical legacy labels that the score-separation model still depends on.

Source contract:

```text
source_agent: Codex (GPT-5)
action: GENERATE_PATCH
title: Wire canonical regime truth into score separation
scope: update read-only ranking and scoring helpers plus focused tests; do not change execution, broker, risk, strategy thresholds, or runtime event loops
requested_paths:
  - core/candidate_scoring.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_scoring.py
  - tests/test_edge_ranking.py
  - docs/agent_reviews/pr3-canonical-regime-score-separation.md
allowed_paths:
  - core/candidate_scoring.py
  - core/expectancy/edge_ranking.py
  - tests/test_candidate_scoring.py
  - tests/test_edge_ranking.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - core/feed*
  - strategies/*
  - config/*
  - dashboard/*
  - main.py
  - run_live.sh
expected_tests:
  - tests/test_candidate_scoring.py
  - tests/test_edge_ranking.py
  - agent review evidence validator
acceptance_proof:
  - canonical router labels such as TRENDING_UP, TRENDING_DOWN, and VOLATILE affect scoring and ranking deterministically
  - analytical legacy labels such as CHOP and HIGH_VOL keep their intended score-separation behavior
  - no execution or broker path is modified
```

## Scope Guard

In scope:

- Make `core.candidate_scoring` accept canonical regime labels without collapsing analytical labels too early.
- Make `core.expectancy.edge_ranking` consume canonical trend labels for regime-mismatch penalties.
- Add focused regression tests for canonical trend/down and volatile routing.

Out of scope:

- No execution changes.
- No order or broker changes.
- No strategy threshold changes.
- No orchestrator/event-loop rewiring.
- No dashboard changes.
- No backtest-module changes.

Boundary verification:

- [x] No broker code touched
- [x] No execution code touched
- [x] No strategy file touched
- [x] No risk gate weakened
- [x] No threshold changed

## Grill Me Review

The real failure mode was not “bad math.” It was translation drift. PR2 normalized regime labels for routers, but the score-separation layer still had its own regime assumptions. That is how a bot ends up labeling a setup `TRENDING_UP` and then scoring it like `UNKNOWN`.

The second failure mode is over-normalization. If `CHOP` gets collapsed into `RANGE` too early, the model stops applying its strongest caution path. This PR preserves those analytical labels where the scoring model still needs the extra specificity.

Verdict: PASS. This is the correct narrow follow-up to PR2.

## Hermes Review

Architecture is improved because the ranking/scoring stack now uses the shared regime canonicalizer instead of silently maintaining a conflicting interpretation layer.

Changed files:

- `core/candidate_scoring.py`
- `core/expectancy/edge_ranking.py`
- `tests/test_candidate_scoring.py`
- `tests/test_edge_ranking.py`
- `docs/agent_reviews/pr3-canonical-regime-score-separation.md`

The change is read-only and deterministic. It does not introduce runtime wiring or broker interaction.

Verdict: PASS.

## GSD Review

Delivery stayed scoped:

- no new runtime path
- no config churn
- no threshold retune
- only regime interpretation hardening in scoring/ranking

Tests were extended only where the new canonical labels needed proof.

Verdict: PASS.

## QA / Safety Review

Safety properties preserved:

- `is_order_action=false`
- `broker_api_called=false`
- no broker adapter imports
- no live execution behavior change
- no fallback or feed gate relaxation

Test proof targets:

- canonical trend labels change ranking consistently
- canonical volatile labels map into the intended high-vol profile
- analytical labels like `CHOP` still preserve conservative scoring behavior

## Acceptance Proof

Commands run:

```bash
python -m pytest -q tests/test_candidate_scoring.py tests/test_edge_ranking.py
python scripts/validate_agent_review_evidence.py
```

Observed result before merge:

- focused ranking/scoring suite passed locally: `35 passed`

Acceptance expectations:

- `TRENDING_UP` and `TRENDING_DOWN` no longer degrade into score-separation blind spots
- `VOLATILE` is no longer ignored by the scoring profile layer
- `CHOP` still applies the strong directional penalty instead of silently downgrading to plain `RANGE`

## Runtime Proof Required After Merge

No live runtime proof is required for this PR because the change is confined to read-only scoring and ranking helpers.

Runtime observation becomes relevant only if a later PR wires these score components into actual runtime decision gates or live opportunity publication.

## What This PR Does Not Prove

This PR does not prove market alpha.

It does not prove the regime classifier itself is institution-grade.

It does not prove strategy profitability.

It does not fix execution realism, fill handling, or orchestrator recovery.

It only proves the current read-only score-separation logic now consumes regime truth more coherently.

## Human Approval

Human approval is required before merge.

Reviewers should verify that preserving `CHOP`, `HIGH_VOL`, `LOW_VOL`, and other analytical labels is consistent with desk intent and that later PRs do not collapse those labels prematurely.


## High-Risk Path Review

N/A
