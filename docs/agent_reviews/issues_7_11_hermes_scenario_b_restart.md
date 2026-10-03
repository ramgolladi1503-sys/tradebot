# Hermes Contract — Scenario B Mid-Session Restart Composition

**source_agent:** hermes
**action:** DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES
**title:** Compose verified same-session CAS inheritance with completed-bar restore after restart
**scope:** tests-only deterministic offline integration; no production behavior changes
**requested_paths:** `tests/test_issues_7_11_scenario_b_restart.py` and Issues 7–11 evidence artifacts
**allowed_paths:** the requested test and campaign evidence files
**forbidden_paths:** production source, strategy semantics, feed/risk/broker/order paths, credentials, token-universe configuration, PR #936
**expected_tests:** one positive mid-session restart composition and fail-closed adversarial companion cases
**acceptance_proof:** actual durable bar store, actual same-session heritage verifier/loader, actual runtime snapshot producer, actual read-only CAS consumer; exact identity/time cutoffs; authority closed
**authority:** `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `paper_authorized=false`, `live_authorized=false`, `allowed_for_live_execution=false`

## Repository trace

Existing tests separately show (a) `MarketSessionStore` restores only completed same-session bars to C1 memory after process-local buffer loss and (b) `runtime_snapshot_producer` consumes verified same-session CAS references after restart. The CAS input is passed to the read-only `_evaluate_cas` consumer. No single cross-issue test currently composes the durable bar restore and heritage-backed CAS restart in one controlled restart scenario.

## Contract

1. Use synthetic, hash-bound source events and a temporary SQLite store. Label all fixture evidence synthetic; it cannot establish historical source authority.
2. Simulate restart by constructing fresh store/consumer state and clearing process-local bars. Do not claim an actual service/process restart.
3. At the CAS contract's 15:14 evaluation boundary, the loader may return only verified same-trading-session CAS references with matching NIFTY token/source identity. The runtime snapshot producer must still require a fresh exact NIFTY spot quote and healthy transport. Earlier evaluation remains pending under the existing cutoff rule.
4. At the allowed evaluation boundary, the read-only CAS consumer must accept recovered input as advisory data only with paper/live/order authority closed.
5. Restored completed bars must be same-symbol, same-date and complete at the causal cutoff. Historical rows cannot satisfy current-feed freshness. No cross-date, corrupted or ambiguous heritage may produce CAS input.
6. Preserve candidate/strategy thresholds and instrument configuration. The integration asserts infrastructure readiness/evaluator input, not a trade or profitability.
7. Current market-row validity/time-sanity and feed-runtime payload are deterministic synthetic inputs injected at the consumer boundary; these prove gate behavior, not production adapter wiring or live feed parity.

## Acceptance proof

- Positive: after simulated mid-session restart, verified same-session primitives reach the actual read-only CAS evaluator; completed NIFTY bars restore from a fresh store and the C1 memory reader can consume them under explicit fresh current-row proof. At 15:14, preserve the existing C1 `OUT_OF_WINDOW` result; the separate in-window restart integration remains the evidence that C1 can qualify during its configured window.
- Negative: cross-date, corrupted and conflicting same-session heritage; unhealthy/mismatched current spot; pre-15:14 CAS evaluation; and incomplete/future bars are rejected or remain pending under their existing contracts.
- Existing `tests/test_market_heritage_graph.py::test_same_session_cas_conflicting_valid_captures_are_blocked` also covers conflicting same-session sources; this composition test repeats that attack through its own fixture.
- All checks use temporary fixtures and make zero broker/order calls; authority remains closed.
- The report explicitly limits results to synthetic offline code-path evidence. Actual service restart, historical source authority, captured/live parity and campaign-wide completion remain UNKNOWN/open.

**Hermes verdict:** tests-only composition approved within this boundary. This cannot promote synthetic evidence to historical or live proof.
