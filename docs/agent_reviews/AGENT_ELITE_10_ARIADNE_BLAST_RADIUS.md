# AGENT-ELITE-10 — Ariadne Blast-Radius Mapper

mode: REVIEW
candidate_id: AGENT-ELITE-10-ARIADNE-BLAST-RADIUS-MAPPER
decision: review_pending
reason: ariadne_static_blast_radius_mapping
source: docs/agent_reviews/AGENT_ELITE_10_ARIADNE_BLAST_RADIUS.md
timestamp: 2026-05-28T18:50:00Z
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

Issue: #382
Parent: #372
Depends on: #381 / PR #397 / merge commit 23fbccf459355ac04e89a114b332180e00c17696

## Agent Work Contract

This PR implements AGENT-ELITE-10 only.

The work adds a static Ariadne blast-radius mapper that converts a root-cause cluster into affected files, likely callers, related tests, related evidence artifacts, candidate-flow stage, safety-boundary relevance, explicit unknowns, and Daedalus-ready payload fields.

It must not run product runtime code, call brokers, modify broker code, change strategy/ranking formulas, change dashboard/UI behavior, or propose a code patch.

## Scope Guard

Allowed:

- Add `tools/code_excellence/ariadne/blast_radius.py`.
- Export the mapper from `tools/code_excellence/ariadne/__init__.py`.
- Add focused tests in `tests/test_ariadne_blast_radius.py`.
- Add this agent-review evidence file.

Not allowed:

- Runtime execution.
- Broker calls.
- Broker code changes.
- Strategy/ranking formula changes.
- Dashboard/UI changes.
- Code mutation engine.
- Runtime module imports.
- External agent calls.
- Test skip/xfail.

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

Question: Does this fix failed tests?

Answer: No. It maps possible blast radius from an existing Ariadne cluster so a future fix can avoid adjacent-path damage.

Question: Does this modify code based on the blast-radius result?

Answer: No. It returns structured static output only.

Question: What happens when blast radius cannot be inferred?

Answer: The result is marked UNKNOWN and includes explicit unknown categories.

Question: Can Daedalus consume this later?

Answer: Yes. The mapper emits a `daedalus_input` payload with cluster identity, confidence, stage, boundary relevance, affected files, proof, and unknowns.

Question: Does this import Tradebot runtime modules?

Answer: No. It imports Ariadne cluster models only.

## Hermes Review

The implementation is intentionally additive:

- Adds `BlastRadius`.
- Adds `map_blast_radius(...)`.
- Maps websocket/feed concepts to feed-start and market-data paths.
- Maps ranking evidence concepts to scoring, ranking, decision-reader, and dashboard-reader paths.
- Marks unknown blast radius explicitly.
- Emits a Daedalus-ready payload without proposing a patch.

## GSD Review

Smallest safe implementation:

- Keep Ariadne blast-radius logic isolated under `tools/code_excellence/ariadne/`.
- No integration into CI gates yet.
- No remediation planner behavior.
- No repo mutation behavior.
- Deterministic pure parsing/mapping tests only.

Files changed:

- `tools/code_excellence/ariadne/__init__.py`
- `tools/code_excellence/ariadne/blast_radius.py`
- `tests/test_ariadne_blast_radius.py`
- `docs/agent_reviews/AGENT_ELITE_10_ARIADNE_BLAST_RADIUS.md`

## QA / Safety Review

Focused command:

```bash
PYTHONPATH=. pytest tests/test_ariadne_blast_radius.py -q
```

Recommended command:

```bash
PYTHONPATH=. pytest tests/test_ariadne_failure_clustering.py tests/test_ariadne_blast_radius.py -q
```

Safety assertions:

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

- Websocket fixture clusters map to websocket tests and feed-start boundary.
- Ranking evidence clusters map to scoring, ranking, decision-reader, and dashboard-reader paths when referenced.
- Unknown blast radius remains UNKNOWN and lists explicit unknown categories.
- Daedalus can consume the structured blast-radius payload later.

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
