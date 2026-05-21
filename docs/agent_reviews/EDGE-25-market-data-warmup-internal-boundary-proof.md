# EDGE-25 — Market Data Warmup Internal Boundary Proof

## Evidence Contract Fields

- mode: PAPER_EVIDENCE_PROOF
- candidate_id: EDGE-25-market-data-warmup-internal-boundary-proof
- decision: ADD_MARKET_DATA_WARMUP_INTERNAL_BOUNDARY_PROOF
- reason: EDGE-24 runtime proof reached ORCHESTRATOR_WARMUP_MARKET_DATA_STARTED but did not reach ORCHESTRATOR_WARMUP_MARKET_DATA_COMPLETED, proving the startup hang is inside core.market_data.ensure_startup_warmup_bootstrap().
- timestamp: 2026-05-21T17:10:00Z
- is_order_action: false
- broker_api_called: false
- live_order_action: false
- broker_order_action: false
- source: docs/agent_reviews/EDGE-25-market-data-warmup-internal-boundary-proof.md

## Review Type

- [x] Pre-merge review
- [ ] Retrospective review

## Agent Work Contract

- PR: EDGE-25 / PR #178 planned
- Branch: edge25-market-warmup-proof
- Scope: add evidence-only internal boundary proof for market-data startup warmup.
- Allowed files:
  - core/market_data_warmup_probe.py
  - core/runtime_startup_lifecycle.py
  - tests/test_market_data_warmup_probe.py
  - docs/agent_reviews/EDGE-25-market-data-warmup-internal-boundary-proof.md
- Forbidden files:
  - core/market_data.py
  - core/orchestrator.py
  - core/kite_depth_ws.py
  - core/auth.py
  - strategies/
  - dashboard/
  - config/
- Forbidden behaviors:
  - No strategy logic changes.
  - No feed/WebSocket behavior changes.
  - No broker/order behavior changes.
  - No market-data functional behavior changes.
  - No dashboard changes.
  - No threshold/ranking/scoring changes.
- Acceptance tests:
  - Probe emits success events for warmup entry, symbol resolution, seed start/completion, symbol seed start/completion, indicators start/completion, and warmup completion.
  - Probe emits failure events when symbol seed fails.
- Runtime proof required: clean off-market PAPER run after merge must show which market-data warmup internal boundary is the last reached.

## Scope Guard

Verdict: PASS

Checked:

- No broker placement changes.
- No LIVE mode enablement.
- No strategy/scoring/threshold changes.
- No dashboard changes.
- No credential handling changes.
- No direct edits to core/market_data.py.
- No direct edits to core/orchestrator.py.
- No fake runtime proof.

Blocking issues: none.

## High-Risk Path Review

Verdict: PASS_WITH_SCOPE_GUARD

High-risk area touched:

- Runtime startup lifecycle installer now best-effort activates the market-data warmup probe.

High-risk areas intentionally not touched:

- core/market_data.py is not edited.
- core/orchestrator.py is not edited.
- broker/feed/auth/strategy/dashboard files are not edited.

Safety proof:

- The probe records start/completion/failure only.
- Return values are preserved.
- Exceptions are re-raised after FAILED evidence is recorded.
- All evidence records remain is_order_action=false.

## Grill Me Review

Verdict: PASS_WITH_RUNTIME_PROOF_REQUIRED

Weak assumptions:

1. Assumption: wrapping the already-imported market-data module is enough to expose the stall.
   - Risk: if the startup path holds a direct pre-wrapper reference, internal events may not appear.
2. Assumption: the next stall is inside seed_ohlc_buffers_on_startup() or _warm_seed_ohlc_from_history().
   - Evidence: EDGE-24 proved ensure_startup_warmup_bootstrap() was entered and did not return.

Failure modes:

1. If MARKET_DATA_WARMUP_ENTERED appears but MARKET_DATA_WARMUP_SEED_STARTED does not, the hang is before seed startup.
2. If MARKET_DATA_WARMUP_SYMBOL_SEED_STARTED appears but no completion/failure appears, the hang is inside historical seed.
3. If MARKET_DATA_WARMUP_INDICATORS_STARTED appears but no completion/failure appears, the hang is inside indicator computation.

Missing proof:

1. Runtime proof after merge must show the last market-data warmup boundary reached.
2. This PR does not fix the warmup stall.

## Hermes Review

Verdict: PASS

Architecture consistency:

1. Adds a small dedicated warmup probe module instead of rewriting the large market_data.py file.
2. Activation remains best-effort and evidence-only.
3. The wrapper preserves return values and exception behavior.

Files not touched:

1. core/market_data.py
2. core/orchestrator.py
3. core/kite_depth_ws.py
4. strategies/

Boundary verdict:

- Evidence-only wrapper around existing market-data warmup functions.
- No business behavior change intended.

## GSD Review

Verdict: PASS

Execution plan:

1. Add market-data warmup probe module.
2. Activate it from runtime startup lifecycle startup probe installation.
3. Add focused tests for success and failure event emission.
4. Add mandatory agent evidence doc.
5. After merge, run clean PAPER/off-market proof.

Evidence required:

1. CI unit tests pass.
2. Agent Review Evidence Gate passes.
3. Runtime proof after merge shows internal market-data warmup boundary events.

Done means:

- The next run tells whether the warmup stall is before symbol resolution, inside seed startup, inside per-symbol historical seed, inside indicator compute, or after seed completion.

## QA / Safety Review

Tests required:

```bash
python -m pytest tests/test_market_data_warmup_probe.py -q
python scripts/validate_agent_review_evidence.py --base-ref origin/main
```

Safety checks:

1. No order action fields set true.
2. No broker/order behavior introduced.
3. No feed/WebSocket behavior changed.
4. No strategy behavior changed.

## Acceptance Proof

Commands:

```bash
python -m pytest tests/test_market_data_warmup_probe.py -q
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

nohup python main.py > .runtime/logs/offmarket_after_edge25_$(date +%Y%m%d_%H%M%S).log 2>&1 &
echo $! > .runtime/offmarket_after_edge25.pid
sleep 60
kill "$(cat .runtime/offmarket_after_edge25.pid)" 2>/dev/null || true
rm -f .runtime/offmarket_after_edge25.pid

grep -nE "MARKET_DATA_WARMUP|ORCHESTRATOR_WARMUP|ORCHESTRATOR_INIT|LIVE_MONITORING|RUNTIME_STATUS" .runtime/logs/runtime_startup_lifecycle.jsonl | tail -220
```

Expected evidence:

```text
MARKET_DATA_WARMUP_ENTERED
Then the last completed/started internal boundary identifies the next blocker.
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
