# Fix WS1006 Recovery-State Consistency and Ranked Pipeline Evidence

mode: REVIEW
candidate_id: PR-FIX-WS1006-RECOVERY-STATE-CONSISTENCY-RANKED-EVIDENCE
decision: add_read_only_runtime_consistency_and_ranked_evidence
reason: Live audit evidence showed an invalid mixed feed state after WS1006 recovery (`RUNNING/LIVE/ticks_flowing/ws_connected=true` coexisting with `ws1006_process_restart_required`), and ranked pipeline evidence was not being emitted during live candidate cycles. This PR normalizes blocked-state snapshots to fail closed and emits read-only ranked pipeline runtime evidence without changing strategy, ranking, Phase2, broker/order, or UI behavior.
timestamp: 2026-06-04T00:00:00Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/fix-ws1006-recovery-state-consistency-ranked-evidence.md

Status: DRAFT (do not merge without explicit human approval)

## Agent Work Contract

### Source Agent

```text
source_agent: Codex (GPT-5.2)
action: GENERATE_PATCH (evidence-only runtime normalization + ranked evidence wiring + deterministic tests)
title: Fix WS1006 recovery-state consistency and ranked pipeline evidence emission
scope: normalize blocked feed snapshots so live/RUNNING cannot coexist with ws1006_process_restart_required, preserve clean recovery transitions, and persist ranked pipeline runtime evidence during live candidate cycles
requested_paths:
  - core/kite_depth_ws.py
  - core/feed/runtime_store.py
  - core/orchestrator.py
  - tests/test_kite_depth_restart.py
  - tests/test_feed_runtime_states.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_ranked_pipeline_runtime_evidence_wiring.py
  - docs/agent_reviews/fix-ws1006-recovery-state-consistency-ranked-evidence.md
allowed_paths:
  - core/kite_depth_ws.py
  - core/feed/runtime_store.py
  - core/orchestrator.py
  - tests/test_kite_depth_restart.py
  - tests/test_feed_runtime_states.py
  - tests/test_kite_depth_ws_stability.py
  - tests/test_ranked_pipeline_runtime_evidence_wiring.py
  - docs/agent_reviews/*
forbidden_paths:
  - core/broker*
  - core/order*
  - core/execution*
  - core/risk*
  - strategies/*
  - config/*
  - dashboard/*
  - run_live.sh
expected_tests:
  - websocket recovery-state normalization tests
  - feed runtime snapshot normalization tests
  - ranked pipeline evidence wiring tests
  - full pytest suite
  - agent review evidence validator
  - unified CE gates
acceptance_proof:
  - blocked WS1006 snapshots are normalized to RECOVERY_BLOCKED with a non-LIVE state machine and no mixed RUNNING/LIVE state
  - a verified recovery clears stale ws1006_process_restart_required metadata before the next clean snapshot
  - ranked_pipeline_runtime_latest.json and ranked_pipeline_runtime_*.jsonl are emitted during live candidate cycles without changing ranking math or Phase2 behavior
  - safety flags are preserved
  - read_only=true
  - append=false
  - is_order_action=false
  - broker_api_called=false
```

## Purpose

Live audit session `live_audit_20260604_091620` showed a WS1006 recovery-state consistency failure: the feed could report `RUNNING/LIVE/ticks_flowing/ws_connected=true` while still carrying `ws1006_process_restart_required`. The same live audit also showed ranked pipeline runtime evidence was not being written when ranked candidates were produced. This PR fixes those evidence contracts only.

## Files Changed

- `/Users/madhuram/tradebot/core/kite_depth_ws.py`
  - Normalizes blocked WS1006 snapshots so mixed LIVE/RUNNING state cannot coexist with `ws1006_process_restart_required`.
  - Keeps the blocked state machine explicit instead of allowing a later generic `ws_disconnected` overwrite.
  - Clears stale reconnect-blocked metadata after verified recovery.
- `/Users/madhuram/tradebot/core/feed/runtime_store.py`
  - Canonicalizes persisted runtime artifacts so blocked WS1006 payloads remain `RECOVERY_BLOCKED` in the latest JSON artifacts.
- `/Users/madhuram/tradebot/core/orchestrator.py`
  - Writes ranked pipeline runtime evidence during live candidate cycles using the existing ranked evidence writer, without changing ranking or Phase2 decisions.
- `/Users/madhuram/tradebot/tests/test_kite_depth_restart.py`
  - Verifies blocked-state emission, recovery clearing, and clean follow-up snapshot behavior.
- `/Users/madhuram/tradebot/tests/test_feed_runtime_states.py`
  - Verifies blocked-state normalization in the persisted feed runtime artifact.
- `/Users/madhuram/tradebot/tests/test_kite_depth_ws_stability.py`
  - Verifies WS1006 terminal-fault behavior remains fail-closed and does not restart in-process.
- `/Users/madhuram/tradebot/tests/test_ranked_pipeline_runtime_evidence_wiring.py`
  - Verifies the orchestrator invokes the ranked evidence writer for runtime ranked reports and keeps the payload read-only.
- `/Users/madhuram/tradebot/docs/agent_reviews/fix-ws1006-recovery-state-consistency-ranked-evidence.md`
  - Records scope, safety review, and acceptance criteria.

## High-Risk Path Review

High-risk files changed:
- `/Users/madhuram/tradebot/core/kite_depth_ws.py`
- `/Users/madhuram/tradebot/core/orchestrator.py`

Review outcome:
- The WS1006 fix is defensive normalization only; it does not re-enable restart behavior or alter feed recovery policy.
- The ranked pipeline evidence wiring only writes read-only artifacts when ranked candidates already exist.
- Failures in evidence writing remain non-fatal.

Residual risk:
- If a downstream caller writes an inconsistent payload outside these paths, the runtime store still fails closed and normalizes only the fields it understands.

## Scope Guard

### In Scope

- Normalize WS1006 blocked-state snapshots so `RUNNING/LIVE/ticks_flowing/ws_connected=true` cannot coexist with `ws1006_process_restart_required`.
- Preserve explicit blocked-state evidence with `RECOVERY_BLOCKED`.
- Clear stale WS1006 recovery metadata after verified recovery.
- Emit ranked pipeline runtime evidence files during live candidate cycles.

### Out of Scope

- Strategy formulas
- Ranking math
- Phase2 candidate selection
- Broker/order behavior
- Dashboard/UI work
- Threshold tuning
- Feed/restart policy changes beyond evidence-state normalization

### Boundary Verification

- [x] No broker calls added
- [x] No order actions added
- [x] No gate bypass added
- [x] No candidate counts are faked
- [x] No strategy behavior changed
- [x] No ranking or Phase2 behavior changed

## Grill Me Review

### Risks Addressed

- The feed runtime artifact can no longer advertise a clean LIVE state while carrying a blocked WS1006 recovery reason.
- Recovery metadata is cleared only after verification, not opportunistically during an unverified reconnect.
- Ranked pipeline evidence is read-only and is emitted only from existing candidate cycles.

### Verdict

PASS — evidence normalization and read-only evidence emission only.

## Hermes Review

### Contract / Architecture Check

- [x] Evidence schema is explicit and versioned.
- [x] Writer provenance is included.
- [x] Safety flags are present.
- [x] Blocked-state evidence remains fail-closed.
- [x] Ranked pipeline evidence does not mutate ranking or Phase2 behavior.

### Verdict

PASS

## GSD Review

### Delivery Check

- [x] Tests prove blocked-state normalization.
- [x] Tests prove recovery clears stale WS1006 metadata before a clean follow-up snapshot.
- [x] Tests prove ranked pipeline evidence writer invocation from the orchestrator.
- [x] No runtime behavior outside evidence normalization changed.

### Verdict

PASS

## QA / Safety Review

Non-negotiables reaffirmed:
- No broker/order code touched.
- No live-order behavior changed.
- No strategy formula or threshold changes.
- No ranking or Phase2 behavior changes.
- No UI changes.
- No restart storm re-enabled.

Evidence/runtime flags preserved:
- `read_only=true`
- `append=false`
- `is_order_action=false`
- `broker_api_called=false`

## Acceptance Proof

### Evidence Contract

The artifacts now include:
- blocked-state normalization to `RECOVERY_BLOCKED`
- explicit WS1006 recovery metadata
- clean recovery metadata clearing on verified success
- ranked pipeline runtime latest JSON
- ranked pipeline runtime daily JSONL
- safety flags

### Commands Run

```bash
PYTHONPATH=. pytest -q tests/test_kite_depth_restart.py tests/test_feed_runtime_states.py tests/test_kite_depth_ws_stability.py tests/test_ranked_pipeline_runtime_evidence_wiring.py
PYTHONPATH=. pytest -q tests
python scripts/validate_agent_review_evidence.py
git diff --check
PYTHONPATH=. python scripts/run_unified_ce_gates.py
```

## Runtime Proof Required After Merge

Required next live verification:
- run an observation-only live session during market hours
- confirm a WS1006 recovery block shows `RECOVERY_BLOCKED` and never a mixed `RUNNING/LIVE/ticks_flowing` state
- confirm a verified recovery clears `ws1006_process_restart_required`
- confirm `logs/ranked_pipeline_runtime_latest.json` and `logs/ranked_pipeline_runtime_*.jsonl` are written during live candidate cycles

## What This PR Does Not Prove

- It does not prove strategy quality improved.
- It does not prove ranking math changed.
- It does not prove Phase2 output changed.
- It does not prove broker connectivity improved.
- It does not prove websocket recovery should be retried in-process.

## Human Approval

Required before merge:
- explicit human review of the WS1006 state normalization
- explicit human review of the ranked evidence wiring
- explicit confirmation that live verification matches the evidence contract
