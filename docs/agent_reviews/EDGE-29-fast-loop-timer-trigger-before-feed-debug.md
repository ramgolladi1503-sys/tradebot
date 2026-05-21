# EDGE-29 — Fast Loop Timer Trigger Before Feed Debug

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-29-fast-loop-timer-trigger-before-feed-debug
- decision: FIX_FAST_LOOP_TIMER_TRIGGER_BEFORE_HEAVY_FEED_DEBUG
- reason: Debug forensics proved startup reached live monitoring but did not prove cycle start. Code inspection showed the fast loop calls the heavy feed-debug path before checking whether the timer cycle is already due. The first timer cycle should not depend on heavy diagnostic feed inspection.
- timestamp: 2026-05-21T21:20:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-29-fast-loop-timer-trigger-before-feed-debug.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: pending
- Branch: edge29-fast-loop-timer-trigger-before-feed-debug
- Scope: make the fast loop honor due timer cycles before consulting heavy feed diagnostics.
- Allowed files:
  - core/execution_core_fast.py
  - tests/test_execution_core_fast.py
  - docs/agent_reviews/EDGE-29-fast-loop-timer-trigger-before-feed-debug.md
- Forbidden files:
  - strategies/
  - dashboard/
  - main.py
  - core/orchestrator.py
  - core/orchestrator_parts/cycle.py
  - core/execution_engine_fast.py
  - core/feed_debug.py
  - config/
- Forbidden behaviors:
  - No strategy changes.
  - No dashboard changes.
  - No feed-debug rewrite.
  - No configuration changes.
  - No order behavior changes.
  - No architecture/probe expansion.

## Scope Guard

Verdict: PASS

Checked:

- The first due timer cycle now returns before calling latest_feed_epoch().
- Feed-triggered cycle behavior is preserved when the timer is not due.
- Idle behavior is preserved when neither timer nor feed changed.
- Existing public method signatures are unchanged.
- No runtime evidence contract is changed.

Blocking issues: none.

## Grill Me Review

Verdict: PASS

Hard challenge:

1. The prior report could have been solved by adding another probe.
   - Rejected. The code already showed a real design flaw.
2. The fast loop should not need heavy diagnostics before the first cycle.
   - Fixed by checking timer due before feed epoch lookup.
3. This must not remove feed-triggered cycles.
   - Preserved: feed epoch is still checked when timer is not due.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. The fix is in the trigger coordinator where the trigger decision belongs.
2. The change is deterministic and tiny.
3. The heavy diagnostics path remains available but is no longer on the timer-due path.
4. No new abstraction is introduced.
5. Tests prove both timer-first and feed-trigger behavior.

## GSD Review

Verdict: PASS

Execution plan:

1. Compute cycle_due before feed_epoch.
2. If cycle_due is true, return immediately using the previous feed epoch.
3. Only call latest_feed_epoch() when timer is not due.
4. Add tests proving the heavy feed-debug path is not called when the timer is due.
5. Add tests proving feed-triggered cycles still run when timer is not due.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_execution_core_fast.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Expected behavior:

1. Timer-due cycle starts without calling latest_feed_epoch().
2. Feed changed still triggers cycle when timer is not due.
3. Feed unchanged and timer not due still idles.

## Acceptance Proof

Acceptance criteria:

1. Agent Review Evidence Gate passes.
2. Code Excellence Gates pass.
3. Unit tests pass.
4. A fresh runtime should pass beyond LIVE_MONITORING_ENTERED to ORCHESTRATOR_CYCLE_STARTED unless the next blocker is downstream.

## Runtime Proof Required After Merge

After merge, run:

```bash
git checkout main
git pull --ff-only origin main
python main.py
```

Then in another terminal:

```bash
cd /Users/madhuram/tradebot
python scripts/debug_forensics.py --profile startup
```

Expected improvement:

```text
last_confirmed_event should move past LIVE_MONITORING_ENTERED
```

## What This PR Does Not Prove

1. It does not prove the downstream cycle completes.
2. It does not prove strategy quality.
3. It does not prove feed health.
4. It does not prove profitability.
5. It does not change dashboard behavior.
6. It does not replace the final architecture documentation PR.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
