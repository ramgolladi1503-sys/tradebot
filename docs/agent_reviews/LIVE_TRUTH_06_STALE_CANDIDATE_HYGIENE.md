# LIVE-TRUTH-06 Stale Candidate Hygiene Agent Review

mode: REVIEW
candidate_id: live_truth_06_stale_candidate_hygiene
decision: review_ready
reason: stale_candidate_hygiene_tests_docs
timestamp: 2026-05-27T12:08:00Z
source: live_truth_06_agent_review

## Agent Work Contract

LIVE-TRUTH-06 adds read-only evidence for stale candidate hygiene.

It classifies candidate evidence as clean, stale, or blocked before later evidence work consumes it.

## Scope Guard

In scope:

- candidate timestamp freshness
- missing timestamp evidence
- future timestamp evidence
- quote age evidence
- feed age evidence
- source artifact age evidence
- explicit stale markers
- candidate container extraction

Out of scope:

- UI changes
- ranking changes
- strategy scoring changes
- lifecycle changes
- feed recovery changes

## Grill Me Review

This PR reports hygiene evidence only and does not change ranking.

## Hermes Review

No external integration, UI change, strategy behavior change, or feed recovery change is added.

## GSD Review

Changed files are limited to one core reducer, one focused test file, docs, agent review evidence, and the roadmap.

## QA / Safety Review

Focused tests cover clean, stale, blocked, timestamp, container, config, writer, and JSON cases.

## Acceptance Proof

`PYTHONPATH=. python -m pytest tests/test_live_truth_06_stale_candidate_hygiene.py`

## Runtime Proof Required After Merge

After merge, this proves only the reducer and evidence writer.

## What This PR Does Not Prove

This PR does not prove later LIVE-TRUTH items.

## Human Approval

Human review is required before broader wiring.

## Next Action

After this PR merges green, continue with LIVE-TRUTH-07.
