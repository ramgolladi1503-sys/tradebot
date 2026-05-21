# EDGE-23 — Orchestrator Constructor Stage Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-23-orchestrator-constructor-stage-proof
- decision: ADD_ORCHESTRATOR_CONSTRUCTOR_STAGE_PROOF
- reason: EDGE-21 runtime proof reached ORCHESTRATOR_INIT_ENTERED but did not reach ORCHESTRATOR_INIT_COMPLETED, ORCHESTRATOR_INIT_FAILED, or LIVE_MONITORING_CALLING.
- timestamp: 2026-05-21T12:05:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-23-orchestrator-constructor-stage-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-23 / PR #176 planned
- Branch: edge23-orch-stage-proof
- Scope: add evidence-only stage proof around the orchestrator constructor and fix stale lifecycle proof flag contamination.
- Allowed files:
  - core/orchestrator_startup_probe.py
  - core/runtime_startup_lifecycle.py
  - tests/test_runtime_startup_lifecycle.py
  - tests/test_orchestrator_startup_probe.py
  - docs/agent_reviews/EDGE-23-orchestrator-constructor-stage-proof.md
- Forbidden files:
  - core/orchestrator.py
  - core/auth.py
  - core/kite_depth_ws.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No broker placement changes.
  - No live order behavior changes.
  - No feed/WebSocket behavior changes.
  - No strategy, ranking, scoring, or threshold changes.
  - No dashboard changes.
- Acceptance tests:
  - Startup lifecycle flags reset when latest payload belongs to an old run.
  - Probe wrapper emits constructor stage events on a fake orchestrator module.
  - Probe wrapper emits failure events when a constructor dependency fails.
- Runtime proof required: clean PAPER/off-market proof after merge must show the last constructor stage reached.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No feed/WebSocket behavior change.
- No direct edits to core/orchestrator.py.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- core/runtime_startup_lifecycle.py affects runtime evidence only.

High-risk area intentionally not touched:

- core/orchestrator.py was not edited because it is large, broker-adjacent, and risky to rewrite for evidence-only debugging.
- core/kite_depth_ws.py was not edited because this PR does not debug feed/WebSocket.
- core/auth.py was not edited because this PR does not alter credential behavior.

Safety proof:

- All emitted lifecycle records keep is_order_action=false.
- The probe wraps constructors/functions only to record start/completion/failure evidence.
- The probe does not change return values or exception behavior.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

Weak assumptions:

1. Assumption: wrapping orchestrator dependency constructors is enough to locate the stall.
   - Risk: the stall could occur in unwrapped code between wrapped stages.
2. Assumption: subclass wrappers preserve behavior for constructor dependencies.
   - Risk: an exact type check could behave differently, although this is unlikely for these startup dependencies.

Failure modes:

1. Probe fails to install before core.orchestrator import.
2. A wrapped dependency blocks before returning, leaving only STARTED without COMPLETED.

Missing proof:

1. Runtime must show stage events after merge.
2. The next clean run must identify the last completed stage and first missing completion.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Keeps proof instrumentation isolated in core/orchestrator_startup_probe.py.
2. Avoids direct edits to the huge orchestrator constructor.
3. Preserves exception behavior by re-raising failures after recording FAILED events.

Files not to touch check:

1. core/orchestrator.py not touched.
2. strategy modules not touched.
3. broker/feed/dashboard code not touched.

Boundary verdict:

- Evidence-only runtime boundary change.
- No execution behavior change intended.

## GSD Review

Verdict: PASS

Execution plan:

1. Reset stale proof_flags when latest payload is from another run.
2. Extend orchestrator startup probe with stage wrappers.
3. Add unit tests for flag reset and fake-module stage wrappers.
4. After merge, run clean PAPER/off-market proof.

Evidence required:

1. CI unit tests pass.
2. Agent Review Evidence Gate passes.
3. Runtime proof after merge shows constructor stage progression.

Done means:

- The next runtime proof identifies whether the constructor is stuck at session guard, trade-log setup, event-log repair, auth warm check, risk state, predictor, execution engine, execution router, gatekeeper, strategy tracker, trade builder, warmup, or depth-start boundary.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_runtime_startup_lifecycle.py tests/test_orchestrator_startup_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Safety checks:

1. No order action fields set true.
2. No broker calls introduced.
3. No live-order behavior introduced.
4. No feed/WebSocket behavior changed.

## Acceptance Proof

Commands:

```bash
python -m pytest tests/test_runtime_startup_lifecycle.py tests/test_orchestrator_startup_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected result:

```text
All tests pass.
AGENT REVIEW EVIDENCE GATE: PASSED
```

## Runtime Proof Required After Merge

Command:

```bash
cd /Users/madhuram/tradebot

git checkout main
git pull --ff-only origin main

rm -f .runtime/locks/kite_session.lock .runtime/locks/live_monitoring.lock .runtime/locks/depth_ws.lock

export TRADING_MODE=PAPER
export EXECUTION_MODE=PAPER
export ALLOW_LIVE_PLACEMENT=false
export DRY_RUN=false

nohup python main.py > .runtime/logs/offmarket_after_edge23_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge23.pid
sleep 60
kill "$(cat .runtime/offmarket_after_edge23.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge23.pid

grep -nE "ORCHESTRATOR_|LIVE_MONITORING|RUNTIME_STATUS" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -160
```

Expected evidence:

```text
The lifecycle log must show the last completed constructor stage and the first stage that started but did not complete, or ORCHESTRATOR_INIT_COMPLETED if constructor returns.
```

## What This PR Does Not Prove

1. It does not prove feed/WebSocket works.
2. It does not prove strategy quality or profitability.
3. It does not prove live execution readiness.
4. It does not fix the constructor stall; it only identifies the blocking stage.
5. It does not prove market-hours cycle behavior while running off-market.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
