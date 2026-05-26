# EDGE-82 — Final Executable Trade Quality Gate

## Purpose

EDGE-82 adds a final read-only executable-quality gate.

The gate answers one question:

`Is the selected ranked candidate still eligible after no-trade, ranking, and executable-truth evidence are checked together?`

This PR does not execute anything. It creates a deterministic evidence contract only.

## Inputs consumed

The gate can consume:

- NoTradeOracle payload/report
- CandidateRankingReport payload/report
- executable-truth decisions or payloads

## Output

`build_final_executable_quality_report(...)` returns a `FinalExecutableQualityReport` with:

- status
- executable quality pass/fail flag
- primary reason
- selected candidate identity
- ordered blockers
- evidence sources
- read-only / no-append markers
- non-action metadata

## Fail-closed rules

The gate blocks when:

- required evidence is missing
- NoTradeOracle requires no-trade
- ranking has no executable candidate
- selected rank still carries blockers, safety flags, or downgrade reasons
- executable-truth evidence is missing
- executable-truth evidence cannot be matched to the selected rank
- executable-truth evidence blocks the selected rank

## Pass rules

The gate passes only when all are true:

- NoTradeOracle is clear
- ranking has an executable candidate
- selected rank has executable bucket and score eligibility
- selected rank has no blocker/safety/downgrade evidence
- executable-truth evidence matches the selected rank
- executable-truth says execution is allowed

## Scope guard

This PR does not:

- call external execution APIs
- submit orders
- create order intent
- mutate runtime state
- append files
- score opportunities
- rank candidates
- change dashboard behavior
- change NoTradeOracle behavior
- change executable-truth behavior

## Test command

`PYTHONPATH=. python -m pytest tests/test_edge_82_final_executable_quality_gate.py`

## Acceptance proof

Tests prove:

- missing evidence fails closed
- no-trade evidence blocks final quality
- ranking without executable candidates blocks final quality
- unsafe selected rank blocks final quality
- missing executable truth blocks final quality
- blocked executable truth blocks final quality
- unmatched executable truth blocks final quality
- clean evidence passes while staying read-only and non-action

## Next PR

EDGE-83 — Paper Truth Journal.

EDGE-83 must not use final executable quality as proof of live readiness. Paper truth must become the source for actual paper outcomes.
