# PR #987 — OptionMate RBFN Scope and Veto Fix

## Agent Work Contract

- `source_agent`: `codex`
- `action`: `GENERATE_PATCH`
- `title`: Keep PR #987 focused on OptionMate RBFN and correct the RP1 upper breakout displacement reference.
- `scope`: Remove Mode 1 Sweep, Mode 2 generic ORB, and Mode 3 derivative-basis paths from this PR; preserve shared Mode 5 dependencies; correct only the volatility-gate displacement reference for the named RP1 upper expansion setup; enforce the completed-bar source timestamp boundary.
- `requested_paths`: `core/sentinel_live_stream_advisor.py`, `core/sentinel_regime_router.py`, `core/analytics/`, `core/market_structure/sentinel_four_vectors.py`, related tests, scope documentation, and generated ORB-only simulation fields.
- `allowed_paths`: Listed runtime files only for removal of the named modes and the explicitly scoped Mode 5 reference/timestamp fixes; related tests and documentation; no credentials, environment, broker, or order paths.
- `forbidden_paths`: Broker/order actions, live-process control, credentials/secrets, weakening risk/quote/freshness/kill gates, changing strategy levels or thresholds, deployment, merge, and production trading.
- `expected_tests`: Focused Mode 5/OptionMate, completed-bar, expiry resolver, router/WAL compatibility, and simulator schema tests.
- `acceptance_proof`: Mode 5 upper expansion uses the frozen RP1 upper boundary only for volatility displacement; missing reference fails closed; strict `2.5 × ATR60` comparison, TD-based confidence, premium cap, and quote freshness stay unchanged; deleted modes have no runtime dispatch; WAL bit positions remain backward compatible.

No canonical Epic/Feature IDs were supplied. Per the user's direction, this work is scoped to existing PR #987; no hierarchy IDs were invented.

## Scope Guard

Mode 1 liquidity sweep, Mode 2 generic ORB dispatch/permission, and Mode 3 basis strategy are removed from PR #987. The Mode 2-only regime permission and ORB-only report/dashboard fields are removed. The unrelated `RegimeCalibrationEngine` analytics feature, its exclusive tests, and its work-item claims are excluded from this PR. Its historical `UNFILTERED_ORB_BASELINE` identity was not renamed or rewritten.

Mode 5 remains first in the dispatch ladder. Its OptionMate opening-range evidence checks, shared regime router/WAL, expiry calendar resolver, Mode 1.5 reversal code, and Mode 4 midday module remain unchanged except where they share the explicitly listed code. The shared expiry resolver stays because the scheduler consumes it. WAL bit 0 remains reserved; existing APM, reversal, and global permission bits keep their assignments.

## Grill Me Review

The adversarial review found no Mode 5 runtime consumer of the calibration engine and no hidden import beyond the module, two calibration-only tests, and its work-item documentation. It approved excluding that entire analytics feature while preserving the shared router and WAL. It also required keeping the historical trial identity unchanged.

The Mode 1/2/3 branches are downstream alternatives in the dispatch ladder; removing them does not unblock or suppress a qualified Mode 5 setup. Mode 5 OR evidence validation and downstream quote/risk gates remain active.

## Hermes Review

The gate-local displacement mapping applies only to `RP1_UPPER_10M_EXPANSION_BREAKOUT` and uses the signal's frozen `rp1_upper` snapshot. Other setup families retain their existing displacement behavior. An absent or invalid RP reference fails closed. The `2.5 × ATR60` threshold, strict comparison, TD-based confidence input, option premium cap, and quote freshness checks are unchanged.

Completed-bar source validation accepts a timestamp exactly at the validated bar boundary and rejects any later timestamp, including `+1 ms`. The same boundary is applied to target and companion OR evidence. Missing or invalid boundary metadata fails closed.

## GSD Review

The implementation removes the requested strategy paths and their exclusive components, retains shared dependencies, adds boundary and frozen-reference tests, and updates the related contract documents. No configuration keys were added. No strategy levels, entry thresholds, ATR multiplier, confidence scoring, target/stop logic, broker behavior, or execution permissions were changed.

## QA / Safety Review

- Focused command covering advisor hardening, OptionMate execution hardening, router/WAL tests: **154 passed**.
- Broader related suite: **33 passed, 4 failed**. The in-flight exit assertion and two dynamic-gear expectations were reproduced on the clean baseline. The October replay test is blocked because the required October journals are absent. These are not reported as passing.
- Simulator contract test confirmed removal of `orb_green_bars` and ORB permissions while preserving the other simulation fields.
- JSON structural comparison confirmed the simulation report changed only by removing `orb_green_bars` and ORB permission entries. The separate multi-session analytics report was accidentally regenerated during test activity, restored to the original PR version, and independently confirmed clean.
- `git diff --check` passed. Dashboard syntax and the changed JSON report parse checks passed.
- No broker API was called, no order action was taken, and the live capture/dashboard processes were not controlled.

## High-Risk Path Review

This change touches `core/sentinel_live_stream_advisor.py`, a live-advisor path. The human-authorized scope is limited to removing the explicitly requested Mode 1/2/3 paths, correcting the named RP1 upper breakout's gate-local volatility displacement, and enforcing the completed-bar boundary. Mode 5's existing quote, premium, ATR, confidence, and execution gates remain in force. The patch does not place orders, call broker APIs, change live configuration, change credentials, or authorize live execution.

Residual risk: the fixed RP1 boundary may allow a candidate to proceed past `VOLATILITY_EXHAUSTED`, after which any existing downstream gate may still veto it. This local test evidence does not establish that a live quote will pass all gates or produce a fill.

## Acceptance Proof

- Frozen RP1 boundary is captured by the named Mode 5 breakout producer and used by the volatility gate.
- Missing boundary is explicitly tested as fail-closed.
- Existing strict ATR cutoff behavior and TD-based confidence input are covered by tests.
- Completed-boundary equality and `+1 ms` rejection are covered for target and companion evidence.
- New WAL records leave bit 0 clear; a legacy record with bit 0 set replays without restoring an ORB permission.
- Mode 1/2/3 runtime symbols and their dedicated exclusive implementations are absent from the changed advisor path.
- At tested head `452e1237fc696210f6c0ce6ee9947c08fe04ae21`, CI completed with blockers: unit-test collection errors, three Code Excellence blocks, trusted-base evidence/runtime findings, and a separate CodeQL alert. No merge-readiness claim is made here; consult PR #987 for checks on the latest head.

## Runtime Proof Required After Merge

After an authorized deployment/restart, an operator must inspect the read-only Forensic Decision Journal for a candidate using the named RP1 upper breakout and verify: frozen boundary provenance, ATR and displacement inputs, all subsequent veto reasons, candidate quote freshness, and final dispatch status. Confirm emitted versus vetoed events without inferring fills from candidates. This PR does not authorize a live restart, deployment, or trade.

## What This PR Does Not Prove

- It does not prove profitability, positive expectancy, fill quality, or an executable market edge.
- It does not prove that all 31,902 previously reported veto events represent distinct setups or trades; the local journal counts are per-contract evaluations and differ by snapshot cutoff.
- It does not prove a live trade will pass the premium cap or remaining downstream gates.
- It does not modify reversal prices, Trend Decider values, strategy thresholds, or risk limits.
- It does not supersede Mode 1.5 or Mode 4, deploy code, restart live processes, or authorize broker/order actions.

## Human Approval

The user explicitly authorized work on PR #987, removal of Modes 1/2/3 from its scope, and implementation/update of the identified live-veto fix. The user also selected the triggering RP1/RP2 boundary mapping; this implementation applies the RP1 boundary only to the named upper expansion setup. Merge, deployment, live-process control, and order actions were not authorized.

## Evidence Contract

- `mode`: `READ_ONLY`
- `is_order_action`: `false`
- `broker_api_called`: `false`
- `allowed_for_live_execution`: `false`
- `append`: `false`
