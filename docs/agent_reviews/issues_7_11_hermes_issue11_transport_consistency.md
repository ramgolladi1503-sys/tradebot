# Hermes Addendum — Issue 11 shared transport consistency

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES
**title:** Preserve authoritative effective websocket health for the CAS bridge
**scope:** Narrow CAS shared-feed transport decision in `core/runtime_snapshot_producer.py`
**repository SHA at contract:** `d1251433d76b8ea70e3cd3fc042fbb2f342e8c95`

## Finding

The current CAS bridge marks shared transport healthy when either
`effective_ws_connected` or legacy `ws_connected` is true. This permits a
contradiction (`effective_ws_connected=false`, `ws_connected=true`) to pass
even though the effective field is the canonical health decision.

## Contract

1. If the validated feed-runtime payload contains `effective_ws_connected`,
   only the exact boolean `True` permits the CAS bridge. False, null, malformed,
   or any other value blocks it, even if `ws_connected` is true.
2. For backward compatibility, use `ws_connected is True` only when the
   effective field is absent. Do not coerce truthy values.
3. Preserve the existing global connected/recovered safety boundary and all
   candidate-local NIFTY evidence checks. Do not modify feed health producers,
   artifacts, freshness limits, runtime wiring, ranking, or execution paths.
4. A blocked bridge emits the existing explicit
   `cas_shared_feed_unhealthy_or_unknown` reason and must not create CAS input
   or evaluator artifacts.

## Acceptance proof

- Actual producer-to-evaluator regression with contradictory fields blocks.
- Exact effective `True` is accepted; legacy-only exact `ws_connected=True`
  remains accepted for compatibility.
- An isolated OR-logic mutant is killed by the contradictory-field regression.
- Focused tests, existing Issue 11 gate mutation, static checks, and broad
  offline regression are run against the final source SHA.
- No live parity or broker/execution authority is inferred.

## Authority

`read_only=true`, `is_order_action=false`, `broker_api_called=false`,
`allowed_for_live_execution=false`, `paper_authorized=false`,
`live_authorized=false`, and `append=false` for evidence contracts.
