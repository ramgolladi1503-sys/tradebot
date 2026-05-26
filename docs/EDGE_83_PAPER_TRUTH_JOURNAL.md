# EDGE-83 — Paper Truth Journal

## Purpose

EDGE-83 creates the canonical paper-truth journal foundation.

The journal is the source of truth for paper-mode events. Later PRs can derive paper state and outcomes from this append-only journal, but this PR does not build reducers, expectancy, slippage truth, dashboard views, or live-pilot behavior.

## What changed

Added `core/paper_truth_journal.py` with:

- `PaperTruthEvent`
- `PaperTruthJournalValidation`
- `build_paper_truth_event(...)`
- `append_paper_truth_event(...)`
- `read_paper_truth_events(...)`
- `validate_paper_truth_events(...)`
- `validate_paper_truth_journal(...)`

## Event model

Each journal event includes:

- schema version
- source
- event id
- event type
- sequence
- timestamp
- mode
- candidate id
- strategy id
- symbol
- side
- optional quantity
- optional price
- previous event hash
- event hash
- payload
- metadata
- non-action metadata

## Supported event types

- `PAPER_CANDIDATE_ACCEPTED`
- `PAPER_ENTRY_RECORDED`
- `PAPER_EXIT_RECORDED`
- `PAPER_REJECTED`
- `PAPER_NOTE_RECORDED`

## Validation rules

The journal validates:

- required fields
- paper-only mode
- valid event type
- positive sequence
- sequence continuity
- previous hash linkage
- event hash integrity
- JSON Lines parseability

## Scope guard

This PR does not:

- call external execution APIs
- submit live orders
- create live order intent
- mutate broker state
- score opportunities
- rank candidates
- reduce paper outcomes
- compute expectancy
- compute slippage truth
- change dashboard behavior
- wire into runtime loops

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_83_paper_truth_journal.py`

## Acceptance proof

Tests prove:

- deterministic event id/hash generation
- non-action metadata remains false
- append/read/validate sequence works
- previous hash links are preserved
- tampered event hashes are detected
- sequence gaps are detected
- previous-hash mismatch is detected
- invalid existing journals block appends
- invalid event type and live mode are rejected
- invalid JSON lines are rejected

## Next PR

EDGE-84 — Outcome Reducer.

EDGE-84 should consume this journal and derive paper state. It must not replace the journal as truth.
