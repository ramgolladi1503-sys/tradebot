# TradeBot Feed Robustness — Antigravity Handoff

## Original objective

Prove and improve TradeBot feed robustness without confusing passing unit tests with live-market reliability.

## Completed Codex implementation

The feed-persistence proof is complete in this branch lineage:

- `c3c2e888` — `fix: make tick persistence shutdown drain-aware`
- `81246ff1` — `test: isolate tick persistence state across feed suites`
- `42fa298f` — `docs: record drain-aware persistence recovery proof`

## Root cause previously resolved

The earlier async persistence failure was a shutdown-contract problem, not corruption or `EMFILE`.

Confirmed failure shape:

- the async persistence worker previously used a fixed two-second shutdown join;
- under intermittent stalls, shutdown returned with queued and in-flight writes still outstanding;
- the worker was still alive at timeout;
- the worker was daemon-based;
- the failure was a partial-drain shutdown failure.

## Persistence remediation already completed

The completed remediation now proves:

- explicit drain-aware shutdown results;
- `COMPLETE_DRAIN`;
- `INCOMPLETE_DRAIN_TIMEOUT`;
- retryable timeout handling;
- immutable timeout snapshot evidence;
- same-worker cleanup;
- synchronized queue / in-flight / pending accounting;
- successful sufficient-deadline recovery.

## Tests already completed

Validated suite:

```bash
/Users/madhuram/tradebot/.venv/bin/python -m pytest -q \
  tests/test_feed_robustness_replay_runner.py \
  tests/test_kite_depth_ws_stability.py \
  tests/test_feed_fd_trace.py \
  tests/test_ws_tick_ingestion_updates_tick_store.py \
  tests/test_tick_store.py \
  --tb=long
```

Result:

```text
83 passed
```

## Existing runtime evidence

Input:

- path: `/Users/madhuram/tradebot/.runtime/market_data/upstox_full_ticks_20260709.parquet`
- SHA-256: `62410f680b0621c836e3b18e8a509126e3dfbcf40c61e3cc23d5c2bc30b95139`

Replay evidence:

- row count: `100,000`
- timestamp fidelity: passed
- pressure profiles: no-pressure, constant-delay, short-deadline intermittent, sufficient-deadline intermittent
- strict verdict: `100K_ASYNC_PERSISTENCE_PRESSURE_RECOVERY_PASS`
- known limitations: no live websocket recovery proof, no provider completeness proof, no full-session soak, no ranking freshness proof, no execution freshness proof, no overall production readiness proof

Semantic hashes:

- canonical semantic hash: `9eefbd54d8a88201c4398b9d43b2e8c07f01c77947c7bed5ceb3a6aff8d7cf9d`
- final per-token-state hash: `f103a7d35c540fd19ce74f422cd409f4305c0042acfcf038927fff4bd931b5b5`

## Current Antigravity objective

Antigravity must continue with:

- disconnect detection;
- single reconnect ownership;
- bounded reconnect attempts;
- complete required-token resubscription;
- duplicate-subscription prevention;
- connected-but-stale correctness;
- post-reconnect per-token freshness;
- partial recovery blocking;
- provider timestamp preservation;
- duplicate/out-of-order tick policy;
- multi-cycle reconnect resource stability.

Task slug:

```text
feed-websocket-reconnect
```

Antigravity branch:

```text
agent/antigravity-feed-websocket-reconnect
```

Antigravity worktree:

```text
/Users/madhuram/.antigravity/worktrees/tradebot/feed-websocket-reconnect
```

## Behavior deliberately not changed

Do not conflate the reconnect gate with unrelated system work. The following remain out of scope:

- strategy logic;
- candidate logic;
- ranking logic;
- risk limits;
- broker order routing;
- manual approval;
- execution behavior;
- UI;
- backtesting.

## Expected high-conflict files

Antigravity will likely need to inspect:

- `core/kite_depth_ws.py`
- `core/market_data.py`
- orchestrator feed startup/shutdown files
- feed freshness modules
- subscription registries
- `tests/test_kite_depth_ws_stability.py`
- `tests/test_ws_tick_ingestion_updates_tick_store.py`

## Ownership boundary

Antigravity is the active writer for reconnect-related files.
Codex is review-only until Antigravity produces a committed handback.

## Files Antigravity should not modify without proof

The following remain protected unless a new reconnect test proves a persistence regression:

- `core/tick_store.py`
- strategy modules
- ranking modules
- risk modules
- execution modules

## Known limitations

Do not over-claim from the deterministic replay evidence:

- deterministic replay does not prove live provider completeness;
- websocket connection does not mean market data is fresh;
- reconnect callback success does not prove all required tokens recovered;
- partial token recovery must keep dependent execution blocked;
- full-session live soak remains a separate gate;
- ranking and execution freshness remain separate proofs.

## Handoff rules

- Codex must not modify Antigravity-owned reconnect files until Antigravity produces a committed handback.
- Codex may later review committed Antigravity work, run adversarial validation, and request changes.
- Antigravity must begin from `/Users/madhuram/.antigravity/worktrees/tradebot/feed-websocket-reconnect`.
- Before every Antigravity work session:

```bash
pwd
git branch --show-current
git status --short
```
