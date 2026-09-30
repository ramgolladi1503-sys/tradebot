# Live Persistence Drain Hardening & Parquet Footer Finalization (PR #942)

mode: SIM
candidate_id: 942-mros-live-drain-parquet-feed-hardening-v1
decision: harden_live_drain_and_finalize_parquet_footer
reason: Eliminate READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE by scaling drain deadline from 0.5s to 10.0s, rate-limit runtime snapshots in on_ticks to 1.0s to prevent SQLite queue saturation, and enforce atomic sync flush and PAR1 footer validation in parquet collector before exit.
timestamp: 2026-09-30T16:50:00+05:30
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/942-mros-live-drain-parquet-feed-hardening-v1.md

## Agent Work Contract

- `source_agent`: Hermes (Architecture & Invariant Contracts) -> GSD (Scoped Execution & Verification)
- `action`: `DEFINE_CONTRACT`, `GENERATE_TESTS`, `GENERATE_PATCH`, `UPDATE_DOCS`
- `title`: Harden live persistence drain, rate-limit runtime snapshot writes, and finalize parquet footer
- `scope`: `core/kite_read_only_observation_runtime.py`, `core/kite_depth_ws.py`, `scripts/tick_data_collector.py`, `tests/test_parquet_collector_finalization.py`, `docs/agent_reviews/942-mros-live-drain-parquet-feed-hardening-v1.md`
- `requested_paths`: `core/kite_read_only_observation_runtime.py`, `core/kite_depth_ws.py`, `scripts/tick_data_collector.py`, `tests/test_parquet_collector_finalization.py`, `docs/agent_reviews/942-mros-live-drain-parquet-feed-hardening-v1.md`
- `allowed_paths`: `core/kite_read_only_observation_runtime.py`, `core/kite_depth_ws.py`, `scripts/tick_data_collector.py`, `tests/test_parquet_collector_finalization.py`, `docs/agent_reviews/942-mros-live-drain-parquet-feed-hardening-v1.md`
- `forbidden_paths`: broker adapters, credentials, order routing, risk gates, live mode enablement, strategies, config
- `expected_tests`: `tests/test_kite_read_only_observation_runtime.py`, `tests/test_parquet_collector_finalization.py`, `tests/test_kite_depth_ws_observation_on_ticks.py`
- `acceptance_proof`: Local test suite passes (47 tests passed), zero compilation errors, agent review evidence gate passes, zero order actions.

## Scope Guard

In scope:
- `core/kite_read_only_observation_runtime.py`: Expand minimum drain deadline from 0.5s to 10.0s to allow backlog drain.
- `core/kite_depth_ws.py`: Rate-limit `_persist_runtime_snapshot_row` in `on_ticks` to at most 1 write/sec.
- `scripts/tick_data_collector.py`: Add `finalize_and_close_parquet()` with flush barrier, `writer.close()`, and `b"PAR1"` footer validation before `os._exit(0)`.
- `tests/test_parquet_collector_finalization.py`: Atomic unit test for clean parquet closure and footer validation.
- `docs/agent_reviews/942-mros-live-drain-parquet-feed-hardening-v1.md`: Mandatory agent review evidence contract.

Out of scope:
- Live broker order routing, account trading execution, strategy threshold modifications, risk gate weakening, production kill switches.

## Grill Me Review

Verdict: PASS
Blocking issues: NO
Analysis:
- The entire pipeline operates in strictly read-only observation mode (`broker_write_authority = false`, `order_authority = false`, `is_order_action = false`, `broker_api_called = false`).
- Zero broker trade authority: order placement, modification, and cancellation APIs are completely absent and forbidden.
- Drain timeout: Expanding the minimum drain deadline to 10.0s gives the SQLite background worker adequate time to commit up to 200,000 tick rows without terminating prematurely with exit code 120 (`READ_ONLY_SHUTDOWN_DRAIN_INCOMPLETE`).
- Parquet footer: Explicit sync flush and `b"PAR1"` magic byte verification prevents corrupted parquet files from abrupt Python process exits.

## Hermes Review

Verdict: PASS
Blocking issues: NO
Design Approach:
- Decoupled tick throughput from SQLite write queue depth by throttling opportunistic runtime state snapshots in `on_ticks` to 1.0s.
- Clean process shutdown protocol: Flush memory buffer -> Close Parquet writer -> Assert valid footer bytes -> Signal exit.
- Preservation of read-only observation invariants across all modified runtime modules.

## GSD Review

Verdict: PASS
Blocking issues: NO
Implementation Status:
- All modified modules compiled cleanly with zero errors.
- Unit tests pass: 47 passed across `test_kite_read_only_observation_runtime.py`, `test_kite_depth_ws_observation_on_ticks.py`, and `test_parquet_collector_finalization.py`.

## QA / Safety Review

Verdict: PASS
Blocking issues: NO
Testing and Boundaries:
- Unit tests: `tests/test_kite_read_only_observation_runtime.py`, `tests/test_parquet_collector_finalization.py`, `tests/test_kite_depth_ws_observation_on_ticks.py` (47/47 passed).
- Compilation: `python3 -m compileall core scripts tests`.
- Boundaries: `is_order_action = false`, `broker_api_called = false`, `read_only = true`. Zero orders placed, modified, or cancelled.

## Acceptance Proof

```bash
pytest -v tests/test_kite_read_only_observation_runtime.py tests/test_parquet_collector_finalization.py tests/test_kite_depth_ws_observation_on_ticks.py
python3 -m compileall core scripts tests
python3 scripts/validate_agent_review_evidence.py --base-ref origin/main --candidate-ref HEAD
```

## Runtime Proof Required After Merge

Run preflight verification:
```bash
python3 scripts/run_governed_morning_observer_v1.py --preflight-only
```
Verify ReleaseStore certified SHA and cron execution at 08:45 AM IST (03:15 UTC).

## What This PR Does Not Prove

This PR does not prove live trading profitability, alpha generation, or order execution fills. It provides hardened, governed, read-only observation infrastructure.

## Human Approval

Approved by human operator for merge, data capture automation, and governed read-only observation.

## High-Risk Path Review

High-risk path modified: `core/kite_depth_ws.py`.
- Nature of modification: Throttling `_persist_runtime_snapshot_row` inside `on_ticks` callback to maximum once per 1.0s.
- Verification: Preserves all websocket message processing, tick reception, mode command verification, and depth dispatch without dropping any incoming market ticks.
- Invariants maintained: Strictly read-only observation (`broker_write_authority = false`, `order_authority = false`, `is_order_action = false`, `broker_api_called = false`).
