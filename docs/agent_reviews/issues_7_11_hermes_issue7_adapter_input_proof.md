# Hermes Stage 1 — Issue 7 adapter prerequisite input proof

**source_agent:** hermes
**action:** DEFINE_CONTRACT, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS
**title:** Prove verified T-1 values are retained by the actual shadow adapters
**scope:** Offline Scenario A test assertion only; no production behavior change.

## MAP

`core/kite_read_only_observation_runtime.py::run_observation` loads pinned T-1 prerequisites and passes each typed value into `StrategyShadowAdapterRegistry`. The registry constructs `IntradayOpeningDriveShadowAdapter` and `OvernightDriftShadowAdapter`, whose instances retain these values as decision inputs. Scenario A already loads a synthetic pinned manifest, constructs the real registry and dispatches a pulse to the adapters, but its assertions prove readiness and invocation without comparing retained adapter inputs to the loader output.

## Contract

Extend only `tests/test_market_heritage_graph.py::test_scenario_a_verified_t1_clean_boot_reaches_shadow_evaluators` to assert exact equality between every verified T-1 loader value supplied to the registry and the corresponding real adapter instance fields for all three dependent strategies. Also assert the nonempty current target expiry from the synthetic launch-plan input reaches the Opening Drive adapter; this expiry is not a T-1 loader value. Keep the fixture explicitly synthetic. Do not assert a candidate/trade signal, alter production adapters, or infer historical source authority.

## Acceptance proof

The test fails if a registry wiring regression substitutes, omits, or misroutes the verified T-1 values (opening-drive prior futures key/close and overnight prior close/SMA200) or the separate current target-expiry input. It still proves adapter invocation and closed authorities. A malformed/missing/mismatched source remains fail-closed under existing loader tests.

## Safety and limits

Tests-only. No config, source data, production runtime, strategy semantics, market data, broker/order/risk/live authority changes. This does not establish that authoritative 2026-09-30 futures data exists or prove captured/live Issue 7 readiness; those remain UNKNOWN.
