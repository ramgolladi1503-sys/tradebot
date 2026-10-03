# GSD Stage 2 plan — Issue 9 strategy memory runtime bridge

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Restore causal completed-bar memory to C1/C2 after restart
**scope:** Execute only the Hermes contract in `docs/agent_reviews/issues_7_11_hermes_issue9_runtime_bridge.md`.

## Files in scope

- `core/market_session_memory_contract.py`: expose an idempotent, explicit configure operation that connects the existing singleton buffer to the canonical store and is called at the existing normal runtime boundary before market-data updates.
- `core/market_data.py`: validate trusted LTP source identity and source-event timestamp before buffer ingestion; use event time and existing LTP age limits, never the cycle cutoff as the bar timestamp.
- `core/market_session_store.py`: add a symbol-scoped, same-date completed-bar snapshot builder backed by `get_bars(as_of=...)`; preserve the existing in-memory API where used elsewhere. Provide explicit freshness input; persisted rows alone never assert fresh feed.
- `core/orchestrator.py`: pass `sym` and explicit live freshness into the snapshot read; remove synthetic memory defaults. Install the bridge in `_legacy_live_monitoring` immediately before market-data fetch. The normal fast cycle delegates through `FastExecutionEngine` to this `run_once` path. Preserve evaluator order, thresholds, candidate/ranking behavior, and fail closed when causal memory is unavailable.
- Focused tests in `tests/core/test_market_session_store.py`, `tests/core/test_market_session_runtime_bridge.py` (including market-data source-time ingestion attacks), and `tests/test_primary_runtime_c1_c2_integration.py`.
- Update `core/candidate_feed_dependencies.py` digest only after final source bytes are stable; run registry and symbol safety suites.
- Update `artifacts/issues_7_11` proof/ledger/verdict artifacts with exact results.

## Forbidden paths

Broker/order/risk/feed producer internals, credentials, environment files, strategy thresholds/evaluator predicates, ranking, token universe, launcher safety gates, Issue 7/8 authority claims, live/paper enablement.

## Execution sequence and current evidence

1. Baseline was recorded from the campaign artifacts; exact broad pre-change run was 8591 passes with three declared exclusions.
2. Added positive and negative tests for durable same-session symbol-specific history, restart read, incomplete-bar cutoff, wrong-symbol/date rejection, absent/stale freshness, runtime singleton attachment, and synthetic fallback rejection.
3. Implemented the bridge using the existing store and explicit pre-fetch runtime initialization point; no import-time installation was added.
4. The legacy C1/C2 integration tests now inject an explicit store snapshot source; a separate test proves missing persisted memory returns no candidates.
5. Attack coverage includes persisted timestamp/hash sabotage in the existing store suite, wrong symbol/date, minute gaps, incomplete cutoff, stale freshness, and absent durable store. Independent review found the pre-validation OHLC ingestion path using cycle time for cached/stale quotes. After an initial repair, independent follow-up identified three more bypasses: off-hours LTP age was not enforced, upstream quote paths synthesized receive time when provider event time was missing, and invalid numeric prices could reach the buffer. Hermes contract amended to cover all three; repair and acceptance validation are in progress.
6. Initial focused verification after the first source-time repair: **87 passed, 1 warning**. Market Session Memory certification: **10/10 gates passed**. These results predate the newly identified bypasses and do not certify the current source.
7. A broad suite was started on the first source-time repair and reported at least one failure before the newly identified blockers; it is not an acceptance result. Rerun after repairs. Exclusions remain the Upstox test requiring unavailable `upstox_client`, the large raw-tick stitched-capture scan, and `test_v5_verifier_deep_primitive_validation` due its earlier external-capture stall.
8. Live/captured-session parity and in-service restart are not proven; keep live status unverified and campaign gate open.

## Acceptance proof

Normal startup writes accepted completed bars to the canonical store; a fresh store instance reconstructs exact same-symbol same-session bars at the causal cutoff; C1/C2 cannot consume another symbol or future/current bar; historical restore cannot satisfy current freshness; unavailable memory cannot synthesize a candidate; strategy semantics and all authority flags are unchanged; all stated tests and registry gates pass.

## Continuation attack — restart, duplicate, late event, derived intervals

A focused post-restart attack was added in `tests/core/test_market_session_runtime_bridge.py`. It writes 15 completed 1-minute rows through trusted source-time ingestion, replays an identical in-progress tick, triggers completion, then injects a late prior-minute tick. A fresh store must preserve the exact 1-minute close sequence and integrity seal, and re-derive three complete 5-minute rows plus one 15-minute row. This exercises supported derived intervals without adding a second persistence format.

Verification: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/core/test_market_session_runtime_bridge.py tests/core/test_market_session_store.py` → 26 passed, 1 warning. The injected late tick returned `REJECTED_LATE_BUCKET`; the finalized durable history remained unchanged after reopen. This remains deterministic offline proof, not actual service restart or captured/live parity.
