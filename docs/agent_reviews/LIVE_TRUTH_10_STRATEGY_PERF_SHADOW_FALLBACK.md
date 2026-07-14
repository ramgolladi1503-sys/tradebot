# LIVE-TRUTH-10 Strategy Perf Shadow Fallback Agent Review

mode: REVIEW
candidate_id: live_truth_10_strategy_perf_shadow_fallback
decision: review_ready
reason: strategy_perf_shadow_fallback_tests_docs
timestamp: 2026-05-27T13:45:00Z
source: live_truth_10_agent_review
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

This review covers LIVE-TRUTH-10 only.

The PR adds read-only evidence for strategy-performance shadow fallback detection. It must not wire runtime behavior, rank candidates, score candidates, alter strategies, alter feed behavior, alter lifecycle state, or call broker APIs.

## Scope Guard

Allowed:

- Add a pure reducer for strategy performance fallback-shadow evidence.
- Add focused unit tests.
- Add documentation and agent-review evidence.
- Shrink `docs/EDGE_TODO.md` for the completed PR.

Not allowed:

- Broker calls.
- Order actions.
- Runtime wiring.
- Dashboard/UI work.
- Ranking/scoring changes.
- Strategy lifecycle changes.
- Feed recovery changes.

## Grill Me Review

Question: Can fallback performance rows silently pass as trusted?

Answer: No. The reducer checks explicit fallback flags and fallback markers in source/reason fields. Any fallback rate above the configured limit produces `STRATEGY_PERF_SHADOW_FALLBACK_SHADOWED`.

Question: Can estimated or recovered performance silently become trusted?

Answer: No. Estimated and recovered rows are counted separately and produce review when their configured rates are exceeded.

Question: Does this PR change live behavior?

Answer: No. It only creates read-only evidence payloads and a writer helper. There is no live runtime wiring.

## Hermes Review

The public contract is intentionally narrow:

- `build_strategy_perf_shadow_fallback_report(...)`
- `write_strategy_perf_shadow_fallback_evidence(...)`

Payloads include schema version, source, status, reason codes, counts, rates, row details, and non-action markers.

## GSD Review

The implementation stays deterministic and local:

- No hidden global state.
- No network calls.
- No broker imports.
- No runtime side effects beyond explicit evidence writing.
- Invalid config and invalid rows fail closed.

## QA / Safety Review

Focused test coverage includes:

- trusted performance rows
- missing performance rows
- invalid payloads
- invalid configuration
- fallback-rate shadowing
- shadow-fallback-rate shadowing
- estimated-rate review
- recovered-rate review
- missing trust-field review
- low-sample shadow review
- nested container extraction
- writer non-action payload
- JSON serialization

## Acceptance Proof

Run:

```bash
pytest tests/test_live_truth_10_strategy_perf_shadow_fallback.py
```

CI must pass before merge.

## Runtime Proof Required After Merge

A later PR may wire this evidence into runtime only if explicitly scoped. That later PR must prove:

- read-only output remains read-only
- broker/order markers remain false
- runtime writes do not append unsafe state
- no ranking/scoring/lifecycle mutation occurs unless separately scoped and reviewed

## What This PR Does Not Prove

This PR does not prove actual strategy profitability, live order safety, ranking quality, feed stability, or lifecycle promotion readiness. It only proves that strategy performance evidence can be inspected for fallback-shadow trust issues.

## Human Approval

Ready for maintainer review after CI is green.

## Next Action

After this PR is merged, continue with `EDGE-88 — Strategy Lifecycle States` only from the latest merged main commit.


## High-Risk Path Review

N/A
