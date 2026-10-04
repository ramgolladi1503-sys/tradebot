# GSD Stage 2 plan — Issue 9 missing-volume authority

**source_agent:** gsd
**action:** PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS
**title:** Keep absent market volume unknown in durable bars
**scope:** Execute only `docs/agent_reviews/issues_7_11_hermes_issue9_volume_authority.md`.
**repository SHA:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Files

- `core/market_data.py`: validate the exact supplied volume as finite and nonnegative; pass valid explicit values with completeness true, and pass absent/invalid volume as unknown with completeness false without rejecting the price tick.
- `tests/core/test_market_session_runtime_bridge.py`: add normal trusted-ingestion → bar-completion → store-reopen coverage for absent, malformed, non-finite, negative, and explicit-zero volume.
- `tests/test_market_data_warm_seed.py`: update the existing assertion that incorrectly codifies missing live-bar volume as numeric zero.
- `artifacts/issues_7_11/`: record exact test and attack outcomes.

## Forbidden scope

`core/ohlc_buffer.py`, volume computation/delta policy, strategy consumers or thresholds, ranking, feed/runtime health gates, risk/order/broker modules, credentials, launchers, token-universe configuration, and unrelated research code.

## Execution

1. Baseline attack: call the trusted ingestion helper with valid LTP and event time but `volume=None`; observe the emitted bar volume and provenance.
2. Add a failing restart-path assertion that missing volume remains `None` after persistence and reopen; add an explicit numeric-volume control.
3. Validate volume only at the ingestion boundary, set per-observation `volume_observation_complete`, and pass invalid volume as `None`; do not change buffer mechanics.
4. Run the focused restart attack, `tests/core/test_market_session_runtime_bridge.py`, and `tests/core/test_market_session_store.py`.
5. Update the warm-seed compatibility assertion to expect null/unknown volume instead of the old fabricated zero.
6. Inspect volume-consuming downstream paths for assumptions that missing volume is numeric; fail closed or preserve existing unknown handling, with no synthetic default.
7. Refresh the source digest in `core/candidate_feed_dependencies.py` only after market-data source bytes are final.
8. Verify exact diff scope, authority flags, and `git diff --check`; document that offline proof does not establish captured/live parity.

## Acceptance

Absent and invalid volume stay null in the finalized durable bar after restart; explicit zero stays zero with completeness true; existing time/source/completion/provenance gates pass; no forbidden file changes occur. This repair does not certify live runtime parity.

## Attack and verification result

The pre-fix bounded probe and new regression both reproduced the defect: valid trusted LTP with `volume=None` created an in-memory bar with volume zero. A neighboring attack confirmed negative/malformed/non-finite volume values must not become complete. The trusted ingestion boundary now marks volume complete only for explicit finite nonnegative values and passes invalid/absent values as `None`, without rejecting the valid price tick.

Verification: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q tests/core/test_canonical_strategy_input_truth.py tests/test_c1_c2_regime_decoupling.py tests/test_primary_runtime_c1_c2_integration.py tests/test_market_data_index_quote_cache.py tests/core/test_market_session_runtime_bridge.py tests/core/test_market_session_store.py tests/analytics/test_issues_7_11_eod_row_parity.py` → 97 passed, 1 warning. Absent and invalid values survived the durable restart with `volume_observation_complete=false`; explicitly supplied zero survived with `true`; persisted integrity passed. The broad regression remains required after this production-source change.

## Final broad regression and isolation repair

The first clean broad run after the production volume fix exposed six historical warm-seed failures. Root cause: explicit test installs and unrelated earlier tests could leave a process-wide durable store attached to the singleton OHLC buffer, while warm-seed unit tests are intended to validate historical seeding independently. Runtime-bridge test installs now restore their prior singleton store, and the warm-seed module explicitly isolates its buffer from durable-store integration. Combined runtime bridge, warm-seed, store, and C1/C2 tests: 60 passed. Broad regression: `PATH=/tmp/tradebot-test-python-bin:$PATH pytest -q --ignore=tests/test_upstox_daily_live_capture.py` → 8614 passed, 9 skipped, 28 deselected, 1474 warnings, exit 0 in 802.86s. The Upstox module remains uncollected because `upstox_client` is unavailable. This does not establish captured/live parity.
