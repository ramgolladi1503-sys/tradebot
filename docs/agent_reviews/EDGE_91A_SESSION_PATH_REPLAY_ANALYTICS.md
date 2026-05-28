# Agent Review — EDGE-91A Session Path Replay Analytics

## Agent Work Contract

Build EDGE-91A as a narrow replay-evidence PR before EDGE-92. The work must remain read-only and deterministic.

## Scope Guard

In scope: `core/replay_session_path.py`, `core/replay_session_path_report.py`, focused tests, docs, and TODO sequencing.

Out of scope: UI changes, runtime wiring, strategy changes, ranking changes, and allocation changes.

## Grill Me Review

The original module alone would be too isolated. The PR includes a report builder so replay rows have a proper read-only evidence surface.

Invalid rows fail closed with explicit reasons instead of fake metrics.

## Hermes Review

Public contracts:

- `SessionPathReplayEvidence`
- `build_session_path_replay_evidence(...)`
- `SessionPathReplayReport`
- `build_session_path_replay_report(...)`

The report exposes schema version, source, status, counts, reasons, evidence rows, and safety flags.

## GSD Review

Purpose: add session-path replay analytics before EDGE-92.

Scope: read-only replay evidence only.

Files changed: `core/replay_session_path.py`, `core/replay_session_path_report.py`, `tests/test_replay_session_path.py`, `docs/EDGE_91A_SESSION_PATH_REPLAY_ANALYTICS.md`, `docs/agent_reviews/EDGE_91A_SESSION_PATH_REPLAY_ANALYTICS.md`, and `docs/EDGE_TODO.md`.

Tests or reason not required: focused tests are required and included.

Evidence: focused pytest coverage proves MFE, MAE, target behavior, give-back behavior, invalid input reasons, report wiring, and safety flags.

Risks: future consumers could misuse this evidence as ranking without a separate ranking PR.

Next PR: EDGE-92 Feed Fault Replay Scenarios after EDGE-91A is merged green.

## QA / Safety Review

Focused tests cover MFE, MAE, target behavior, give-back behavior, session windows, top-mover buckets, invalid input reasons, batch report wiring, and read-only flags.

Required non-action proof: `is_order_action=false`, `broker_api_called=false`, `live_order_action=false`, `broker_order_action=false`.

## Acceptance Proof

Run:

```bash
pytest tests/test_replay_session_path.py -q
```

Expected: all focused tests pass and no UI files are changed.

Evidence auditor fields:

- mode: PAPER
- candidate_id: EDGE-91A-SESSION-PATH-REPLAY
- decision: SESSION_PATH_REPLAY_EVIDENCE_ONLY
- reason: READ_ONLY_REPLAY_ANALYTICS
- timestamp: 2026-05-28T03:15:00Z
- is_order_action: false
- broker_api_called: false
- source: docs/agent_reviews/EDGE_91A_SESSION_PATH_REPLAY_ANALYTICS.md

## Runtime Proof Required After Merge

No runtime proof is required because EDGE-91A is not wired into runtime behavior.

Future consumers must prove their own integration when they consume this evidence report.

## What This PR Does Not Prove

This PR does not prove final ranking quality, feed fault behavior, strategy expectancy, UI behavior, or paper readiness.

It only proves deterministic session-path replay evidence generation.

## Human Approval

Human review is required because EDGE-91A is inserted between EDGE-91 and EDGE-92.

## High-Risk Path Review

high-risk path review: this PR touches `core/`. The new core files are read-only replay evidence modules and do not import UI, runtime, strategy, or ranking modules.
