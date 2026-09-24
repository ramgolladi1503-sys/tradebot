# PR #933 — Independent-recheck-required correction to PR #932

mode: OFFLINE_READ_ONLY
candidate_id: PR933_PR932_CANONICAL_CAS_TRUTH
decision: REVIEW_PENDING_INDEPENDENT_VERIFICATION
reason: Original PR932 qualification, executable-pool, timestamp and replay assertions are not independently supported.
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/pr933_pr932_canonical_truth_review.md

## Source and scope
Correction branch is based on PR932 commit dc0dfa0bb0ae36da99891569013f42d4df7a48fe.
Changes are limited to source and tests for CAS canonical qualification, its session-bound primitive capture, observer integration, and read-only shadow/trade-truth semantics, plus this record and invalidation of earlier proof.

## What the repository actually establishes
- CAS morning reversal feature: ratio of authoritative frozen 10:00 and 09:15 NIFTY primitives, with sign reversal.
- The 15:14 first-executable-underlying-observation window is governed by 2000 ms, separately from the old harness's unrelated 2500 ms threshold.
- CAS_MORNING_REVERSAL_SHORT_HORIZON_V1 is SHADOW_ONLY in governed_strategy_authority; no broker, order, paper or live authority.
- Current canonical read-only registry declares required_underlyings NIFTY. This correction enforces exact equality.
- CASPrimitiveStore produces immutable records containing identity, source/receive timestamps and a record hash.
- A true future signal requires all three frozen 09:15, 10:00 and 15:14 same-day exchange timestamp primitives. Without one, qualification is UNKNOWN or NOT_IN_WINDOW, not PASS.
- A valid strategy observation is not an execution-ready option: actual contract, depth, spread, liquidity, account/portfolio risk and governance evidence remain unassessed.

## Reviewer challenge to implementation
The corrected harness does not consume generic confidence, direction or caller-provided completed-bar flags as qualification. CAS evaluator is called only after verified primitive identity, provenance and timing, and outputs underlying UP/DOWN plus CE/PE advisory mapping. Confidence remains NULL because the evaluator has no calibrated probability output.

A qualified observation may yield a bounded SHADOW_ONLY advisory candidate. That candidate has NULL option entry/SL/target, execution_eligible=false, and no inferred option quote freshness. An advisory-ready record is not a trade-ready record.

The shadow selector no longer manufactures a million-unit default portfolio for a risk PASS. Trade truth distinguishes observed candidate generation from selection; missing exchange/receive timings remain NULL.

## Non-proof / known blockers
1. No new market-data replay or fresh live/prospective test is included here; the unit fixtures are synthetic and only establish logic.
2. PR932 original V1/V2 replay manually injected confidence/direction/completed-bar and contained timestamp contradiction, therefore not proof.
3. PR932 original reported latency values are unsupported constants, not measured pipeline distributions.
4. Registry lists SPOT and FUTURES feeds while the frozen signal feature is calculated on NIFTY index return; this correction does not assert that Futures availability or option execution is verified. Independent authority review is required before any promotion beyond read-only advisory.
5. Existing PR932 parent branch has unrelated protected-runtime scope and baseline CI failures. Do not weaken rules to obtain PASS.
6. CAS decision window demands a genuine 15:14 exchange observation. A minute-cadence observer might miss the 2-second advisory emission window; no claim of operational live readiness is made.

## Required independent checks before integration
- Inspect exact source diff and NIFTY token authority.
- Run the rewritten offline tests and the broader affected contract suites.
- Kill mutations that substitute generic confidence, admit BANKNIFTY, bypass missing 15:14 primitive, promote shadow candidate to executable, accept mismatched pulse clock and invent entry prices.
- Run a real replay with source-bound timestamp data; record input hashes and exact commands, not hand-authored measurements.
- Complete source-derived stage-latency audit, or report UNKNOWN.
- Ensure protected runtime and code-excellence gates are green on the exact candidate SHA or identify precise blocker.

## Safety
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
orders_placed=0 (code path is read-only; not a claim from a new live run)
orders_modified=0
orders_cancelled=0

Verdict: IMPLEMENTATION_UNDER_REVIEW. Not merge-ready, not live-proven, no structural trading edge claimed.
