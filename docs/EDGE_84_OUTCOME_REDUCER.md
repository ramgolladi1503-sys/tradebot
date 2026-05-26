# EDGE-84 — Outcome Reducer

## Purpose

EDGE-84 adds a read-only reducer that derives paper candidate outcomes from the EDGE-83 paper-truth journal.

The journal remains the source of truth. The reducer only validates and derives state from journal events.

## What changed

Added `core/paper_outcome_reducer.py` with:

- `PaperCandidateOutcome`
- `PaperOutcomeReductionReport`
- `reduce_paper_outcomes(...)`
- `reduce_paper_outcomes_from_journal(...)`

## Inputs consumed

The reducer consumes EDGE-83 paper-truth events:

- `PAPER_CANDIDATE_ACCEPTED`
- `PAPER_ENTRY_RECORDED`
- `PAPER_EXIT_RECORDED`
- `PAPER_REJECTED`
- `PAPER_NOTE_RECORDED`

## Outputs derived

For each candidate, the reducer derives:

- candidate id
- strategy id
- symbol
- status
- entry side
- exit side
- quantity
- entry price
- exit price
- gross paper PnL when closed
- first/latest sequence
- event count
- blockers

Report-level fields include:

- journal validity
- event count
- candidate count
- closed/open/rejected/invalid counts
- realized gross PnL
- journal validation payload
- non-action metadata

## Fail-closed behavior

The reducer validates the journal before reducing. If the journal is invalid, the reducer returns `PAPER_OUTCOMES_BLOCKED` and does not derive candidate outcomes.

Invalid inputs include:

- hash mismatch
- sequence gap
- previous-hash mismatch
- invalid event type
- invalid mode
- malformed journal file

## Outcome statuses

- `ACCEPTED`
- `OPEN`
- `CLOSED`
- `REJECTED`
- `NOTE_ONLY`
- `INVALID`

## Scope guard

This PR does not:

- modify the journal
- append paper events
- call external execution APIs
- submit live orders
- create live order intent
- mutate broker state
- score opportunities
- rank candidates
- compute strategy expectancy
- promote or suspend strategies
- compute slippage/cost truth
- change dashboard behavior
- wire into runtime loops

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_84_paper_outcome_reducer.py`

## Acceptance proof

Tests prove:

- closed long candidates derive realized gross paper PnL
- open positions surface open blockers
- rejected candidates reduce to rejected outcomes
- exit-without-entry is invalid
- duplicate entry is invalid
- invalid journal blocks before reduction
- journal-file reduction does not mutate the journal
- report payloads remain JSON serializable
- output remains read-only and non-action

## Next PR

EDGE-85 — Strategy Expectancy by Regime.

EDGE-85 may consume reduced outcomes, but must not change the paper journal or reducer truth contracts.
