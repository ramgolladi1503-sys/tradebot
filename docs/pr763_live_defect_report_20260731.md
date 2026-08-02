# PR #763 Live Defect Report - 2026-07-31

## Run Classification

Run ID: `unified-pr748-756-20260731-98a86d0d77f0-live-98721ee5`

Verdict:

```text
LIVE_DEFECT_OBSERVED
UNIFIED_LIVE_EVIDENCE_PARTIAL_NOT_FORMAL_ACCEPTANCE
```

The run remained read-only. The sealed evidence shows no order action, broker call, or live-execution authority.

## Evidence Accounting

- Total runtime: 141.47 minutes.
- Feed-live duration: 140.03 minutes.
- Degraded duration: 0.56 minutes.
- Longest continuous stable interval: 95.69 minutes.
- Recovery transitions: 9.
- Heartbeat count: 2.
- Safety scan: PASS. No positive order-action, broker-call, or live-execution-authority markers were found in sealed live artifacts.

Artifact seal:

- `SEALED`: present.
- `SHA256SUMS`: present.
- `artifact_manifest.json`: present.
- Manifest artifact count: 21.
- Manifest SHA256: `ca069793a4b2387544393605c219d2c74f268d8c6882a566e8ce252ea4008fd4`.

## Separate PR Verdicts

- PR #748: PARTIAL, NOT ACCEPTED. Market Event Graph stayed `MISSING_SOURCE_BARS`; accepted intervals and graph triggers remained zero.
- PR #749: LIVE DEFECT OBSERVED. The live constituent source was disabled in the governed child, so no completed constituent bars could be produced.
- PR #750: PARTIAL, NOT ACCEPTED. Feed truth and safety evidence were captured, but no formal acceptance is possible without PR #748/#749 source intervals.
- PR #751: PARTIAL, NOT ACCEPTED. No downstream formal validation can be accepted without completed constituent bars.
- PR #752: PARTIAL, NOT ACCEPTED. No downstream formal validation can be accepted without completed constituent bars.
- PR #753: PARTIAL, NOT ACCEPTED. No downstream formal validation can be accepted without completed constituent bars.
- PR #754: PARTIAL, NOT ACCEPTED. Pre-outcome evidence remained read-only, but the constituent-source precondition failed.
- PR #755: PARTIAL, NOT ACCEPTED. No live acceptance evidence can be inferred from the blocked MEG source.
- PR #756: PARTIAL, NOT ACCEPTED. Candidate and ranking artifacts were captured, but the MEG source input remained missing.

## Causal Trace

Expected chain:

```text
WebSocket observation ticks
-> observation-token routing
-> tick persistence/runtime store
-> market_event_graph_tick_reader
-> constituent one-minute aggregation
-> completed interval publication
-> PR #748 MEG bridge
```

First causal break:

```text
governed child environment
-> MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE absent/false
-> attach_market_event_graph_constituent_source returned DISABLED
-> no observation-token routing/subscription evidence
-> no tick reader input
-> no completed constituent bars
-> PR #748 reported MISSING_SOURCE_BARS
```

Evidence:

- `live/research_preoutcome_states.jsonl` has 6,669 rows with `completed_bar_count=0`.
- For NIFTY rows, `constituent_source_status=DISABLED` and `constituent_source_reason=market_event_graph_live_source_disabled`.
- Non-NIFTY rows correctly returned `NOT_APPLICABLE`.
- `live/subscription_events.jsonl` and `live/subscription_registry_samples.jsonl` contain observer rows but no requested-token count, observed-token count, or subscription evidence because the source returned before evidence construction.
- `live/market_event_graph_intervals.jsonl` has 13,338 rows, all `MISSING_SOURCE_BARS` with `completed_constituent_bars_missing`.

## Specific Checks

- All 50 constituent tokens actually subscribed: NOT PROVEN. The governed child never enabled the live constituent source, so the subscription request path did not execute.
- Observation ticks reached the PR #749 reader: NOT PROVEN. The source was disabled before reader setup.
- Token-domain mismatches: NOT EVALUATED. No token-resolution evidence was emitted.
- Timestamp/timezone/session-date mismatches: NOT EVALUATED. The source did not reach minute-boundary evaluation.
- Completed-bar boundary conditions: NOT EVALUATED. The source did not reach aggregation.
- Right-closed interval logic: NOT EVALUATED in this live run. Existing unit tests cover right-closed tick reading.
- Minimum-40-constituent coverage: NOT EVALUATED. The source did not reach coverage checks.
- Runtime-store versus tick-database source mismatch: NOT EVALUATED. The source did not reach the reader.
- Watermark initialized beyond available ticks: NOT EVALUATED. No source state with a live watermark was built.
- Source filtering that accepts options but drops NSE EQ ticks: NOT EVALUATED. Observation routing did not activate.
- Source process writing to a different database or run namespace: NOT EVALUATED. No subscription or reader evidence was emitted.
- Observer hook order: PASS for observer invocation; FAIL for useful evidence because the source returned disabled before evidence construction.
- Exceptions swallowed by constituent producer: NOT OBSERVED. The sealed exception artifacts do not show a constituent reader/producer exception.

## Fix

The governed launcher now sets:

```text
MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true
MARKET_EVENT_GRAPH_LIVE_UNIVERSE_PATH=runtime/reference/market_event_graph/nifty50_live_universe_kite_9fb8832853c27944_828c0c378e493972_fba078a4cd7aeb52.json
```

in the supervised child environment, alongside the existing campaign and read-only flags. This activates PR #749's read-only live constituent-source path without changing thresholds, feed gates, validation rules, order behavior, broker behavior, or strategy parameters.

Regression coverage:

```text
pytest -q tests/test_unified_live_validation_pr748_756_v1.py tests/test_market_event_graph_constituent_source.py
```

Result:

```text
18 passed
```
