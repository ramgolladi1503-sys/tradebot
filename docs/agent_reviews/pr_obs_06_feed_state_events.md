# PR-OBS-06 Agent Review Evidence — Feed Freshness and Fallback Safety Events

mode: paper_review
timestamp: 2026-05-23T08:35:00Z
candidate_id: pr_obs_06_feed_state_events
decision: approve_scoped_feed_state_event_shell
reason: adds_read_only_feed_state_event_shell_without_runtime_wiring_or_execution_side_effects
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false
source: core/observability/feed_state.py

Status: scoped implementation evidence for PR-OBS-06  
Scope: feed freshness and fallback safety event shell only

---

## Agent Work Contract

This PR implements PR-OBS-06 from the Observability Architecture roadmap: Feed Freshness and Fallback Safety Events.

The work contract is limited to:

- add `core/observability/feed_state.py`
- export feed-state helpers from `core/observability/__init__.py`
- add `tests/test_observability_feed_state.py`
- add `docs/observability/FEED_STATE_EVENTS.md`
- add this mandatory agent review evidence file
- keep all behavior read-only and disconnected from live feed runtime, strategy, ranking, risk, dashboard, paper execution, live execution, and broker paths

---

## Scope Guard

In scope:

- `FeedStateEventEmitter`
- `FeedStateEventError`
- `feed.fresh` event construction
- `feed.stale` event construction
- `quote.real` event construction
- `quote.missing` event construction
- `quote.fallback_used` event construction
- `execution.blocked_fallback` event construction
- `execution.blocked_stale_feed` event construction
- optional JSONL write through `ObservabilityJsonLogger`
- reason validation for blocked feed-state events
- invariant validation that recovered fallback or stale feed states cannot be marked executable in observability payloads
- tests proving emitted payloads keep `is_order_action=false` and `broker_api_called=false`

Out of scope:

- runtime feed wiring
- quote recovery behavior
- strategy changes
- ranking changes
- risk changes
- review queue changes
- dashboard changes
- paper execution changes
- live execution changes
- broker calls
- order actions
- OpenTelemetry
- Prometheus
- Grafana, Loki, Tempo, or Jaeger
- evidence aggregation

Files intentionally not touched:

- strategy modules
- ranking modules
- risk modules
- broker modules
- execution modules
- dashboard files
- runtime startup scripts
- market-data feed modules

---

## Grill Me Review

Review stance: challenge whether this PR creates fake feed safety confidence.

Findings:

- The PR does not claim the real feed runtime is instrumented yet.
- The PR does not read live market data or recover missing quotes.
- The PR does not alter candidate executability.
- The PR does not wire events into strategy, ranking, risk, dashboard, or execution paths.
- The PR only creates a tested shell future feed instrumentation can call.
- The emitter uses the existing event schema and JSON logger instead of raw dictionaries.
- Blocked feed-state events require reasons.
- Tests prove recovered fallback and stale feed states cannot be represented as executable by this shell.
- Tests prove emitted payloads remain non-action and broker-free.

Main risk:

- Future work could mistake this shell for proof that live feed runtime is already safe.

Mitigation:

- Documentation and evidence explicitly state that runtime proof requires a later scoped wiring PR.

Verdict: pass for PR-OBS-06 shell scope.

---

## Hermes Review

Review stance: check boundaries, clarity, and maintainability.

Boundary result:

- No feed runtime file changed.
- No strategy file changed.
- No ranking file changed.
- No risk file changed.
- No execution file changed.
- No dashboard file changed.
- No broker file changed.
- No runtime startup file changed.
- No external observability dependency added.

Public API added:

- `FeedStateEventEmitter`
- `FeedStateEventError`

Maintainability notes:

- The emitter owns feed-state observability event construction only.
- The emitter delegates schema validation to `ObservabilityEvent`.
- The emitter delegates JSON output to `ObservabilityJsonLogger`.
- Future feed/runtime wiring should call this emitter rather than duplicating feed/fallback payload logic.

Verdict: pass for handoff quality.

---

## GSD Review

Review stance: judge whether this PR creates useful forward movement without overengineering.

Delivery value:

- Future feed instrumentation can emit feed freshness and quote-source events through one tested path.
- Stale feed and recovered fallback states now have consistent names, stages, decisions, IDs, reasons, and safety fields.
- Future evidence-bundle work can reason over the same feed-state event contract.
- Future safety invariant tests can validate that fallback/stale states do not become executable.

Execution quality:

- The implementation is small.
- The API is explicit.
- No external telemetry stack is introduced.
- No trading behavior is modified.
- Tests cover feed fresh, feed stale, quote source states, blocked states, invariant rejection, JSON writing, and reason validation.

Next PR:

- Continue the Observability Architecture roadmap only after PR-OBS-06 is merged and green.

Verdict: pass.

---

## QA / Safety Review

QA stance: prove this does not weaken the trading system.

Safety checks:

- The emitter does not import broker modules.
- The emitter does not import strategy modules.
- The emitter does not import ranking modules.
- The emitter does not import risk modules.
- The emitter does not import dashboard modules.
- The emitter does not place orders.
- The emitter does not call broker APIs.
- The emitter does not mutate feed or candidate state.
- The emitter emits schema-validated observability events only.
- The emitted payloads preserve explicit non-action safety fields.

Test coverage added:

- feed fresh event is valid and non-action
- feed stale event is blocked with a reason
- quote source events are valid and non-action
- blocked feed-state events preserve candidate ID and reason
- unsafe feed-state flags are rejected
- blocked events require reasons
- JSON logger write emits one line without side effects

Verdict: pass.

---

## Acceptance Proof

Acceptance proof for this PR:

- `core/observability/feed_state.py` defines the feed-state event emitter shell.
- `core/observability/__init__.py` exports the feed-state API.
- `tests/test_observability_feed_state.py` verifies the shell behavior.
- `docs/observability/FEED_STATE_EVENTS.md` records the contract and exclusions.
- Agent evidence includes the required review sections.
- Evidence header includes CE metadata fields.

Expected commands:

```bash
python -m pytest tests/test_observability_feed_state.py tests/test_observability_events.py tests/test_observability_json_logger.py
python scripts/validate_agent_review_evidence.py
```

---

## Runtime Proof Required After Merge

No live feed runtime proof is required for this PR because the emitter shell is intentionally not wired into runtime execution.

Runtime proof becomes required in a future scoped PR that connects feed-state events to safe read-only feed/runtime boundaries.

Future runtime proof should show:

- one feed fresh or feed stale event emitted from the actual safe feed boundary
- one quote real, quote missing, or quote fallback event emitted from the actual safe quote boundary
- one blocked fallback or blocked stale feed event emitted when applicable
- no broker API calls during event emission
- no order actions during event emission
- no strategy, ranking, risk, or execution behavior changes caused by observability emission

---

## What This PR Does Not Prove

This PR does not prove:

- live feed runtime emits observability events
- real quote recovery is safe
- stale feed is blocked in runtime
- recovered fallback is blocked in runtime
- feed freshness evidence is aggregated
- fallback safety evidence is aggregated
- OpenTelemetry works
- Prometheus metrics exist
- Grafana, Loki, Tempo, or Jaeger are configured
- dashboard observability exists
- paper trading stability improved
- trade quality improved
- profitability improved

This PR only adds the read-only feed-state event emitter shell.

---

## Human Approval

User requested continuation after merged PR #204 / PR-OBS-05 and asked to proceed until CI is green after the pull request is created.

This implementation follows the documented PR-OBS-06 roadmap scope and does not cross into runtime wiring, strategy, ranking, risk, dashboard, paper execution, live execution, or broker behavior.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
