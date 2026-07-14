# Agent Review — EDGE-72 Hard Downgrade Engine

## Agent Work Contract

- PR: EDGE-72 — Hard Downgrade Engine
- Scope: read-only hard downgrade decisions after EDGE-71 classified candidate metadata
- Runtime behavior changed: no
- Broker behavior changed: no
- Order behavior changed: no
- Dashboard behavior changed: no
- Strategy execution changed: no
- Ranking behavior changed: no
- Scoring behavior changed: no

## Evidence Contract Fields

```yaml
mode: PAPER
candidate_id: EDGE_72_HARD_DOWNGRADE_ENGINE
message_decision: HARD_DOWNGRADE_ENGINE
decision: HARD_DOWNGRADE_ENGINE
reason: Converts risky classification warnings into advisory-only decisions and invalid or malformed candidate metadata into blocked decisions without runtime wiring, ranking, scoring, broker calls, or order intent.
timestamp: 2026-05-25T17:20:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/edge_72_hard_downgrade_engine.md
```

## Grill Me Review

Challenge: Did this secretly introduce ranking or selection?

Answer: No. The downgrade engine produces categorical readiness decisions only: `CANDIDATE_READY`, `ADVISORY_ONLY`, and `BLOCKED`. It does not assign priority, rank, score, expectancy, confidence boost, edge estimate, or allocation.

Challenge: Why downgrade EDGE-71 warnings instead of leaving them as warnings?

Answer: Because unknown direction, unknown regime, unknown family, and incomplete evidence are not clean candidate inputs. Leaving them as plain warnings would allow future downstream layers to accidentally treat them as ready. EDGE-72 makes the safety consequence explicit.

Challenge: Can invalid classification output pass through?

Answer: No. Invalid EDGE-71 reports produce an invalid EDGE-72 report and zero candidate-ready decisions.

Challenge: Can malformed candidate payloads silently disappear?

Answer: No. Malformed payloads become blocked decisions with explicit blockers.

## Hermes Review

- Decisions are deterministic and JSON serializable.
- Report and decision payloads preserve read-only and non-action fields.
- Advisory-only decisions preserve visibility without pretending candidate metadata is clean.
- Blocked classification rows remain blocked.
- No strategy module path is imported.
- No strategy callable is invoked.

## GSD Review

- Smallest useful step: downgrade decisions only after classification.
- No overengineering: no scorer, no ranker, no selector, no runtime writer, no strategy plugin loader, no dashboard panel.
- No unrelated cleanup.
- Tests cover real EDGE-69 → EDGE-70 → EDGE-71 → EDGE-72 flow, read-only payloads, incomplete evidence downgrade, unknown metadata downgrade, empty input fail-closed behavior, invalid classification fail-closed behavior, classification-blocked row preservation, malformed payload blocking, and metadata-only behavior.

## QA / Safety Review

- Safety boundary: hard downgrade is read-only evidence only.
- Broker boundary: no broker APIs, no live calls, and no broker payload generation.
- Strategy boundary: no strategy modules are imported and no strategy callables are invoked.
- Runtime boundary: no runtime files are written and no runtime decision behavior changes.
- Failure handling: empty input and invalid classification fail closed; malformed rows are blocked; risky warnings become advisory-only.
- Test safety: tests use metadata-only specs and prior candidate contract outputs.

## Scope Guard

This PR must not:

- modify strategy implementations
- wire runtime strategy selection
- call strategy functions
- rank candidates
- score candidates
- select candidates
- allocate capital
- call broker APIs
- add dashboard UI
- mutate runtime artifacts
- weaken existing tests

## Acceptance Proof

```bash
PYTHONPATH=. python -m pytest tests/test_edge_72_hard_downgrade_engine.py tests/test_edge_71_candidate_classification_layer.py tests/test_edge_70_candidate_normalization_dedup.py tests/test_edge_69_strategy_candidate_pool.py
```

## Runtime Proof Required After Merge

No runtime proof is required for EDGE-72 because this PR is not wired into runtime execution.

Future runtime proof is required only when a later scoped PR reads hard downgrade decisions from runtime, ranking, or dashboard code.

## What This PR Does Not Prove

- Strategy profitability
- Strategy expectancy
- Signal quality
- Candidate ranking quality
- Paper/live trading readiness
- Dashboard usability
- Broker/order safety beyond preserving non-action metadata

## Human Approval

Ready for review after CI passes.


## High-Risk Path Review

N/A
