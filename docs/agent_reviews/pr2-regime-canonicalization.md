# PR2 - Regime Canonicalization

mode: PAPER
candidate_id: pr2-regime-canonicalization
signal_id: pr2-regime-canonicalization
strategy_id: regime_canonicalization
decision: REVIEW_ONLY
reason: unify_regime_translation_between_movement_router_and_legacy_bucket_layers
timestamp: 2026-06-15T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr2-regime-canonicalization.md

## Agent Work Contract

This PR creates one shared regime-translation module so movement-regime labels, strategy-router labels, and legacy bucket labels stop drifting independently.

Source contract:

```text
source_agent: Codex (GPT-5)
action: GENERATE_PATCH
title: Unify regime truth translation layers
scope: add a shared read-only regime translator and rewire legacy/router consumers; do not change execution, broker, thresholds, strategy formulas, or market-data snapshot generation
requested_paths:
  - core/regime_canonical.py
  - core/regime_router.py
  - core/regime.py
  - tests/test_regime_router.py
  - tests/test_regime_canonicalization.py
  - docs/agent_reviews/pr2-regime-canonicalization.md
allowed_paths:
  - core/regime_canonical.py
  - core/regime_router.py
  - core/regime.py
  - tests/test_regime_router.py
  - tests/test_regime_canonicalization.py
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
  - run_live.sh
expected_tests:
  - tests/test_regime_router.py
  - tests/test_regime_canonicalization.py
  - tests/test_regime_wrappers.py
  - tests/test_regime_canonical.py
  - tests/test_movement_regime.py
  - tests/test_regime_scoring_profiles.py
  - tests/test_regime_scoring_profile_safety_flags.py
  - agent review evidence validator
acceptance_proof:
  - movement regime labels map deterministically into router labels
  - legacy bucket normalization consumes the same translation source
  - ambiguous trend input still fails closed to UNKNOWN
  - no strategy threshold or execution behavior changes
```

## Scope Guard

In scope:

- Add a shared canonical regime translator.
- Rewire `core.regime_router` to use it.
- Rewire `core.regime.normalize_regime` to use it.
- Add focused tests for movement-label and legacy-bucket normalization.

Out of scope:

- No strategy threshold changes.
- No broker or order code.
- No market-data snapshot rewiring.
- No execution or orchestrator changes.
- No dashboard/UI work.
- No backtest behavior changes.

Boundary verification:

- [x] No broker code touched
- [x] No execution code touched
- [x] No strategy file touched
- [x] No risk gate weakened
- [x] No threshold changed

## Grill Me Review

The failure mode here is subtle drift: one part of the bot sees `TREND_UP`, another expects `TRENDING_UP`, another collapses `VOLATILITY_EXPANSION` into nothing, and candidates disappear or misroute silently.

This PR fixes translation drift, not model quality. It does not claim the regime classifier is institution-grade. It only makes downstream consumers stop disagreeing on label meaning.

The second risk is over-broad remapping. This PR keeps the mapping conservative:

- directional movement regimes map to directional router regimes
- non-directional movement regimes map to `RANGE`
- risk/expansion regimes map to `VOLATILE`
- inconclusive input fails closed to `UNKNOWN`

Verdict: PASS. High leverage, narrow blast radius.

## Hermes Review

Architecture is improved because label translation now has a single owner.

Changed files:

- `core/regime_canonical.py`
- `core/regime_router.py`
- `core/regime.py`
- `tests/test_regime_router.py`
- `tests/test_regime_canonicalization.py`
- `docs/agent_reviews/pr2-regime-canonicalization.md`

No high-risk path review is required under the repo validator rules because this PR does not modify config, auth, feed/WebSocket, orchestrator, execution, risk, or strategy files.

Verdict: PASS.

## GSD Review

Delivery stayed inside the approved slice:

- one new shared translator
- two consumer rewires
- focused regression tests

No generic cleanup was mixed in. No attempt was made to “fix regime quality” in the same PR.

Verdict: PASS.

## QA / Safety Review

Safety properties preserved:

- `is_order_action=false`
- `broker_api_called=false`
- no live-mode change
- no execution-path mutation
- ambiguous trend routing remains fail-closed

Test proof targets:

- movement labels route consistently
- legacy bucket labels normalize consistently
- canonical export excludes `UNKNOWN` from tradable router labels

## Acceptance Proof

Commands run:

```bash
python -m pytest -q tests/test_regime_router.py tests/test_regime_canonicalization.py tests/test_regime_wrappers.py tests/test_regime_canonical.py tests/test_movement_regime.py tests/test_regime_scoring_profiles.py tests/test_regime_scoring_profile_safety_flags.py
python scripts/validate_agent_review_evidence.py
git diff --check
```

Observed result before merge:

- focused regime suite passed locally: `33 passed`

Acceptance expectations:

- movement-regime labels no longer fall through router translation as garbage
- legacy normalization no longer maintains a separate alias table
- wrapper tests and scoring-profile tests remain green

## Runtime Proof Required After Merge

No live runtime proof is required for this PR because it changes only read-only label translation and legacy normalization helpers.

Runtime observation becomes relevant only when later PRs wire canonical regime truth into runtime selection, ranking, or observability surfaces.

## What This PR Does Not Prove

This PR does not prove the regime model is good.

It does not prove the volatility analysis is institution-grade.

It does not fix ranking quality, candidate quality, or backtest quality.

It only proves that the current codebase now translates regime labels through one deterministic shared path instead of several contradictory ones.

## Human Approval

Human approval is required before merge.

Reviewers should verify that the mapping choices for `CHOP`, `COMPRESSION`, `VOLATILITY_EXPANSION`, `TRAP_RISK`, and `EXHAUSTION_RISK` match desk intent before broader regime-routing changes continue in later PRs.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
