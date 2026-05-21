# EDGE-24 — Startup Warmup Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-24-startup-warmup-boundary-proof
- decision: ADD_STARTUP_WARMUP_MARKET_DATA_BOUNDARY_PROOF
- reason: EDGE-23 runtime proof reached ORCHESTRATOR_WARMUP_STARTED but did not reach ORCHESTRATOR_WARMUP_COMPLETED, ORCHESTRATOR_INIT_COMPLETED, or LIVE_MONITORING_CALLING.
- timestamp: 2026-05-21T16:35:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-24-startup-warmup-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-24 / PR #177 planned
- Branch: edge24-startup-warmup-proof
- Scope: add evidence-only boundary proof inside startup warmup by wrapping the market-data warmup bootstrap call used by `Orchestrator._run_startup_warmup_bootstrap()`.
- Allowed files:
  - core/orchestrator_startup_probe.py
  - tests/test_orchestrator_startup_probe.py
  - docs/agent_reviews/EDGE-24-startup-warmup-boundary-proof.md
- Forbidden files:
  - core/orchestrator.py
  - core/market_data.py
  - core/kite_depth_ws.py
  - core/auth.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No strategy logic changes.
  - No feed/WebSocket behavior changes.
  - No broker behavior changes.
  - No order placement behavior changes.
  - No dashboard changes.
  - No threshold/ranking/scoring changes.
- Acceptance tests:
  - Startup probe emits warmup method started/completed events.
  - Startup probe emits market-data warmup started/completed events.
  - Startup probe emits market-data warmup failed events when the wrapped bootstrap raises.
- Runtime proof required: clean off-market PAPER run after merge must show whether the hang is before, inside, or after market-data warmup bootstrap.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No direct edits to core/orchestrator.py.
- No direct edits to core/market_data.py.
- No fake runtime proof.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- `core/orchestrator_startup_probe.py` is runtime evidence instrumentation.

High-risk areas intentionally not touched:

- `core/orchestrator.py` is not edited.
- `core/market_data.py` is not edited.
- Broker/feed/auth/strategy/dashboard files are not edited.

Safety proof:

- The wrapper records start/completion/failure only.
- Return values are preserved.
- Exceptions are re-raised after FAILED evidence is recorded.
- All evidence records remain `is_order_action=false`.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

Weak assumptions:

1. Assumption: the current hang is inside `ensure_startup_warmup_bootstrap()`.
   - Evidence: the latest run stopped at `ORCHESTRATOR_WARMUP_STARTED` and did not reach warmup completion.
2. Assumption: wrapping the module-global function is enough.
   - Evidence: `Orchestrator._run_startup_warmup_bootstrap()` calls the module-global `ensure_startup_warmup_bootstrap(...)`.

Failure modes:

1. If `ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED` appears but no completion/failure appears, the hang is inside market-data warmup.
2. If warmup market-data completes but `ORCHESTRATOR_WARMUP_COMPLETED` is missing, the hang is after bootstrap return inside the warmup method loop/logging.

Missing proof:

1. Runtime proof after merge must show the last warmup boundary reached.
2. This PR does not fix the warmup stall.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Keeps proof logic isolated in `core/orchestrator_startup_probe.py`.
2. Avoids direct changes to the large orchestrator class.
3. Avoids changing market-data warmup behavior.

Files not touched:

1. `core/orchestrator.py`
2. `core/market_data.py`
3. `core/kite_depth_ws.py`
4. `strategies/`

Boundary verdict:

- Evidence-only wrapper around an existing startup dependency.
- No business behavior change intended.

## GSD Review

Verdict: PASS

Execution plan:

1. Add startup probe wrapper for `ensure_startup_warmup_bootstrap`.
2. Add unit tests for success and failure event emission.
3. Add mandatory agent evidence doc.
4. After merge, run clean PAPER/off-market proof.

Evidence required:

1. CI unit tests pass.
2. Agent Review Evidence Gate passes.
3. Runtime proof after merge shows warmup market-data boundary events.

Done means:

- The next run tells whether the warmup stall is inside market-data bootstrap or after the bootstrap returns.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_orchestrator_startup_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Safety checks:

1. No order action fields set true.
2. No broker calls introduced.
3. No feed/WebSocket behavior changed.
4. No strategy behavior changed.

## Acceptance Proof

Commands:

```bash
python -m pytest tests/test_orchestrator_startup_probe.py -q
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
export ORDER_RECON_DAEMON_ENABLE=false

nohup python main.py > .runtime/logs/offmarket_after_edge24_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge24.pid
sleep 60
kill "$(cat .runtime/offmarket_after_edge24.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge24.pid

grep -nE "ORCHESTRATOR_WARMUP|ORCHESTRATOR_INIT|LIVE_MONITORING|RUNTIME_STATUS" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -160
```

Expected evidence:

```text
ORCHESTRATOR_WARMUP_STARTED
ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED
Then either:
- ORCHESTRATOR_WARMUP_MARKET_DATA_COMPLETED, or
- ORCHESTRATOR_WARMUP_MARKET_DATA_FAILED, or
- no completion/failure, proving a hang inside market-data warmup.
```

## What This PR Does Not Prove

1. It does not prove feed/WebSocket works.
2. It does not prove market-hours behavior.
3. It does not prove strategy quality or profitability.
4. It does not fix warmup blocking.
5. It does not fix reconciliation blocking from the normal constructor path.

## Human Approval

Approved by: Ram, after CI passes
Date: 2026-05-21
