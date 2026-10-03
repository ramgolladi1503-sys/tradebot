# Hermes Addendum — Issue 11 CAS spot dependency gate

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Bind CAS advisory input to its declared current NIFTY spot dependency
**repository SHA at contract:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Root-cause trace

`core/candidate_feed_dependencies.py` declares `CAS_MORNING_REVERSAL_SHORT_HORIZON_V1` as requiring exact `INDEX_SPOT/NIFTY` identity and `ADVISORY_ONLY` scope. `core/runtime_snapshot_producer.py` currently bridges the already-captured 09:15/10:00 primitives whenever the canonical feed runtime says the shared websocket is connected. It does not require current NIFTY health. `build_cas_input` receives the cycle timestamp as `observation_timestamp`, so stale/missing current NIFTY evidence can be presented to the evaluator as a current advisory observation.

The read-only observer's same-cycle `market_snapshot` already includes an exact NIFTY symbol/token quote identity, `quote_truth.is_fresh`, `feed_health.status`, and `feed_health.underlying_quote_age_sec`. It uses the existing 2.5-second observer freshness decision based on the provider LTP event timestamp. The snapshot also has `generated_at`; `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC` is already configured to 3.0 seconds.

## Contract

1. Preserve the existing global feed-runtime connected/recovered safety gate. This addendum cannot relax or replace it.
2. Bridge CAS inputs only when the current market snapshot contains exact symbol `NIFTY`, a positive exact-integer quote token equal to the token in both verified CAS primitives, `quote_truth.is_fresh is True`, `quote_truth.is_executable_quote is False`, `feed_health.status == "HEALTHY"`, and an exact finite nonnegative numeric `underlying_quote_age_sec` within the existing configured index/LTP freshness bound.
3. Require an aware `generated_at` whose age is finite, nonnegative, and no greater than existing `FEED_TRUTH_SNAPSHOT_MAX_AGE_SEC`. Missing, malformed, future, or stale snapshots fail closed.
4. A stale unrelated option does not veto this CAS advisory because its verified source declaration requires only NIFTY spot. This remains `ADVISORY_ONLY`; it does not make any option quote valid or executable.
5. A stale, missing, malformed, or token-mismatched NIFTY quote blocks the CAS input. Emit a read-only explicit gate status/reason; do not fabricate zero or substitute cycle time as quote time.
6. Do not edit shared feed classifiers/producers, generic candidate dependency semantics, ranking, option/futures candidates, strategy signal calculations, freshness thresholds, risk/order/broker gates, or token universe.

## Blast radius

| Patch node | Direct callers | Transitive consumers | Runtime artifacts changed | Safety invariants touched | Existing tests | New tests required | Cross-issue risk |
|---|---|---|---|---|---|---|---|
| CAS input bridge gate | `produce_and_store_runtime_snapshots` | `_evaluate_cas` and advisory readiness/artifact | `cas_short_horizon_inputs` presence and read-only gate state/reason | Adds a candidate-local fail-closed dependency requirement; preserves shared transport gate and advisory-only boundary | runtime snapshot producer; CAS producer/evaluator tests | fresh spot + stale option positive path; stale/missing/malformed/token mismatch negative paths; real evaluator invocation only on accepted input | Scenario C/D composition only; no change to unrelated candidates or shared health |

**EXPECTED_CHANGE_SURFACE:** CAS advisory input bridge and its explicit telemetry state.
**MUST_NOT_CHANGE_SURFACE:** candidate calculations, thresholds, shared feed health, ranking, option quote/execution validity, risk/order/broker behavior, token universe.
**OBSERVABILITY_CHANGE_SURFACE:** `cas_input_gate` state/reason.
**ROLLBACK_SURFACE:** remove the additional spot evidence check; existing global connected-websocket gate remains.

## Acceptance proof

- Positive Scenario C composes real CAS primitive construction, actual runtime snapshot producer, and actual CAS evaluator with healthy exact NIFTY spot plus an unrelated stale option. CAS reaches `ADVISORY_ONLY`; option evidence remains stale and no execution authority is created.
- Negative Scenario D changes only required NIFTY spot freshness/identity and proves no CAS input/evaluator artifact is emitted; explicit `cas_input_gate` reason identifies the failure.
- Attack absent identity, bool/string token, stale/future/malformed age, false/non-bool freshness, stale/future/malformed `generated_at`, and stale option with healthy NIFTY.
- Mutating out the required-spot predicate causes the designated stale-underlying regression to fail.
- Run focused producer/CAS tests and broad offline regression. No live/captured parity claim is allowed.

## Authority

`read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `paper_authorized=false`, `live_authorized=false`, `append=false` for evidence contracts. No broker/order calls or authority changes.
