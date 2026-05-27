# LIVE-TRUTH-06 Stale Candidate Hygiene Agent Review

mode: REVIEW
candidate_id: live_truth_06_stale_candidate_hygiene
decision: review_ready
reason: stale_candidate_hygiene_tests_docs
timestamp: 2026-05-27T12:00:00Z
source: live_truth_06_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Work Contract

LIVE-TRUTH-06 adds read-only evidence for stale candidate hygiene.

It classifies candidate evidence as clean, stale, or blocked before later evidence work consumes it.

## Scope

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
- runtime wiring
- ranking changes
- strategy scoring changes
- lifecycle changes
- feed recovery changes

## Review

Grill Me: this PR reports hygiene evidence only and does not change ranking.

Hermes: no external integration, UI change, strategy behavior change, or feed recovery change is added.

GSD: changed files are limited to one core reducer, one focused test file, docs, agent review evidence, and the roadmap.

## QA Evidence

Focused tests cover:

- clean candidates
- no candidates
- stale candidate timestamp
- missing timestamp
- invalid candidate payload
- future timestamp
- stale quote, feed, and source artifact age
- explicit stale marker
- ISO timestamp parsing
- candidate container extraction
- invalid config
- evidence file writing
- JSON serialization

Command:

`PYTHONPATH=. python -m pytest tests/test_live_truth_06_stale_candidate_hygiene.py`

## Next Action

After this PR merges green, continue with LIVE-TRUTH-07 — Latency / SLO Guard Oscillation Evidence.
