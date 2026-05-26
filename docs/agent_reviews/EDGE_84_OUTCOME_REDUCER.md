# EDGE-84 Outcome Reducer Agent Review

mode: REVIEW
candidate_id: edge_84_outcome_reducer
decision: review_ready
reason: paper_outcome_reducer_tests_docs
timestamp: 2026-05-26T18:35:00Z
source: edge84_outcome_reducer
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Work Contract

EDGE-84 derives paper candidate outcomes from the EDGE-83 paper-truth journal.

The journal remains the source of truth. The reducer validates journal evidence first, then derives read-only outcomes.

## In Scope

- Validate paper-truth journal evidence before reduction.
- Derive candidate-level paper outcomes.
- Derive gross paper PnL for closed candidates.
- Surface open, rejected, and invalid outcomes.
- Preserve read-only and non-action metadata.

## Out of Scope

- Journal mutation.
- Paper event appends.
- Expectancy calculations.
- Slippage/cost truth.
- Strategy promotion or suspension.
- Dashboard views.
- Runtime loop wiring.

## Guardrails

- Journal remains truth.
- Reducer is read-only.
- Invalid journals block before outcome derivation.
- No dashboard behavior change.
- No scoring or ranking behavior change.
- No strategy lifecycle decisioning.

## Review Answers

Question: Can this PR write to the journal?

Answer: No. It reads events and returns a derived report only.

Question: Can an invalid journal produce outcomes?

Answer: No. Invalid journal validation returns a blocked report with no outcomes.

Question: Does this PR compute expectancy?

Answer: No. EDGE-85 is responsible for expectancy after this reducer is merged green.

Question: Does this PR make strategy lifecycle decisions?

Answer: No. Promotion/suspension work is later in the roadmap.

## Changed Files

- `core/paper_outcome_reducer.py`
- `tests/test_edge_84_paper_outcome_reducer.py`
- `docs/EDGE_84_OUTCOME_REDUCER.md`
- `docs/agent_reviews/EDGE_84_OUTCOME_REDUCER.md`
- `docs/EDGE_TODO.md`

## Test Evidence

Command:

`PYTHONPATH=. python -m pytest tests/test_edge_84_paper_outcome_reducer.py`

Expected result:

- focused EDGE-84 tests pass
- invalid journals fail closed before reduction
- valid journals derive deterministic paper outcomes
- non-action metadata remains false

## Next Action

After EDGE-84 merges green, continue to EDGE-85 — Strategy Expectancy by Regime.
