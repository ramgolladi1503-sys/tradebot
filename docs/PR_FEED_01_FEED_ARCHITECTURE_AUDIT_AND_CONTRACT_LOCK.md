# PR-FEED-01 — Feed Architecture Audit and Contract Lock

## Purpose

PR-FEED-01 locks the current feed architecture before implementing feed behavior gates.

This PR is audit/contract-lock only. It does not change runtime feed behavior, websocket behavior, subscription behavior, candidate generation, ranking, scoring, dashboard rendering, broker behavior, or order behavior.

## Why this PR exists

Recent EDGE work proved that false executable confidence can come from stale, fallback, subscription-failed, price-mismatched, or display-only data. The product now has quote truth, feed truth, symbol execution safety, freshness visibility, top-opportunity truth, directional-bias audit, and capital-selection evidence.

But feed work still has multiple owners and layers. Before adding hold gates or warmup gates, the project needs one locked feed contract map.

## Current feed architecture owners

### 1. Live feed runtime owner

`core/kite_depth_ws.py` is the current live websocket/depth feed owner.

Responsibilities currently visible from imports and module state:

- Kite ticker setup and runtime websocket process ownership
- Token subscription and desired token tracking
- Runtime feed snapshot writing through `core.feed.runtime_store.write_runtime_snapshot`
- Runtime status overlay publication through `core.runtime_status_overlay`
- Feed restart guard and circuit breaker integration
- Market-data monitor recording for ticks/depth
- Blocker lifecycle integration for feed symbol blockers
- In-memory websocket/tick/depth state such as last websocket tick, last message by token, symbol option tick timestamps, token maps, restart state, and runtime state

This module is the operational owner. It is not the canonical truth contract owner.

### 2. Feed runtime persistence owner

`core/feed/runtime_store.py` is the persistence owner for feed runtime snapshots.

Responsibilities:

- Initializes and writes the `feed_runtime` SQLite table
- Persists websocket connection state, subscribed/intended token counts, token sample, last websocket tick epoch, last depth epoch, runtime state, and last error
- Emits feed startup lifecycle evidence when runtime snapshots are written
- Reads the latest persisted feed runtime snapshot

This module stores runtime evidence. It should not become the policy decision owner.

### 3. Runtime snapshot envelope owner

`core/runtime_snapshot_store.py` is the snapshot-envelope and latest-artifact owner.

Responsibilities:

- Defines paths such as `feed_runtime_latest.json`, `advisory_latest.json`, and `top_opportunities_latest.json`
- Writes and reads snapshot envelopes
- Adds freshness evidence through `read_snapshot_with_freshness(...)`

This module owns artifact freshness wrapping, not feed-health policy.

### 4. Dashboard reader owner

`dashboard/readers/snapshot_reader.py` is the dashboard read boundary.

Responsibilities:

- Reads snapshot envelopes for dashboard callers
- Attaches freshness fields for missing, invalid, stale, or fresh snapshot files
- Normalizes top-opportunity payloads through the top-opportunity executable truth contract

This module is a visibility/reader boundary. It should not own feed-health policy.

### 5. Runtime overlay owner

`core/runtime_status_overlay.py` derives effective websocket status and publishes operator-visible feed unhealthy overlays.

Responsibilities:

- Derives effective websocket connected state
- Derives feed_ok from runtime payload state, websocket state, runtime state, option blockers, and tick/depth age
- Publishes blocked/waiting-cycle-refresh overlays to suggestions, engine-cycle status, and runtime-health files

This module is currently a presentation/overlay policy layer. It overlaps with canonical feed health truth and must be reconciled in PR-FEED-02R.

### 6. Canonical feed truth owner

`core/feed_health_truth.py` is the current canonical read-only feed-health truth contract.

Responsibilities:

- Reconciles global `feed_ok`
- Reconciles `ws_connected` and `effective_ws_connected`
- Reconciles per-symbol option feed blocker reasons
- Reconciles per-symbol option last-tick age
- Emits deterministic global and symbol-level feed truth reasons

This is the contract owner for future FEED behavior gates unless a future PR explicitly replaces it.

### 7. Symbol execution safety owner

`core/symbol_execution_safety.py` consumes canonical feed truth at candidate/symbol level.

Responsibilities:

- Resolves candidate symbol identity
- Extracts feed evidence from candidate fields and source flags
- Calls `classify_feed_health_truth(...)`
- Maps feed truth failures into executable-safety block reasons

This module owns executable-candidate feed safety. It should consume feed truth but not redefine it.

### 8. Quote truth owner

`core/quote_truth.py` is the canonical quote-source and quote-age truth owner.

Responsibilities:

- Classifies trusted live/cache, fallback, subscription-failed, and unknown quote sources
- Detects fallback source, subscription failure, price mismatch, stale option LTP, missing quote age, and no live option feed
- Decides rank and execution eligibility at quote level

Quote truth and feed truth must remain separate:

- Quote truth answers: can this quote be trusted?
- Feed truth answers: is the feed/runtime/symbol stream healthy enough?

## Locked canonical contract ownership

From this PR onward, use this ownership model unless a future PR explicitly changes it:

| Area | Canonical owner | Consumers | Must not own |
| --- | --- | --- | --- |
| Live websocket runtime | `core/kite_depth_ws.py` | feed runtime store, monitors, overlays | Canonical truth policy |
| Feed runtime persistence | `core/feed/runtime_store.py` | diagnostics, dashboard/runtime evidence | Feed policy decisions |
| Latest artifact freshness | `core/runtime_snapshot_store.py` | dashboard readers, UI panels | Feed health truth |
| Dashboard snapshot reading | `dashboard/readers/snapshot_reader.py` | Streamlit/dashboard UI | Runtime feed decisions |
| Runtime overlay visibility | `core/runtime_status_overlay.py` | suggestions/engine/runtime-health files | Canonical feed truth owner |
| Canonical feed health truth | `core/feed_health_truth.py` | symbol execution safety, future feed gates | Websocket mutation, subscription mutation |
| Symbol-level executable feed safety | `core/symbol_execution_safety.py` | executable truth | Live websocket/runtime ownership |
| Quote truth | `core/quote_truth.py` | executable truth, scoring truth | Feed runtime policy |

## Duplicate or overlapping areas to reconcile

### Overlap 1 — feed_ok derivation

`core/runtime_stat-us_overlay.py` derives feed_ok from runtime payload state, websocket state, runtime state, option blockers, and tick/depth age.

`core/feed_health_truth.py` also classifies feed health using global `feed_ok`, websocket state, and option symbol evidence.

Reconciliation required in PR-FEED-02R:

- Feed truth must be canonical.
- Overlay can format or publish the decision but must not silently diverge.
- Runtime payload can provide inputs, but not override unsafe canonical truth.

### Overlap 2 — websocket connected vs effective websocket connected

Runtime overlay has `derive_effective_ws_connected(...)`.

Feed truth currently accepts `effective_ws_connected` first and falls back to `ws_connected`.

Reconciliation required:

- Define which layer derives `effective_ws_connected`.
- Ensure canonical feed truth receives or computes the same value consistently.
- Do not let raw `ws_connected=true` hide state-machine DOWN/no-message conditions.

### Overlap 3 — per-symbol option blocker and option tick freshness

`core/feed_health_truth.py` consumes:

- `option_feed_block_reason_by_symbol`
- `option_last_tick_age_by_symbol`
- `symbol_feed_ok_by_symbol`
- `feed_ok_by_symbol`

`core/kite_depth_ws.py` tracks symbol option tick timestamps and runtime subscription state.

Reconciliation required:

- Runtime owner must publish consistent per-symbol evidence.
- Feed truth must consume it deterministically.
- Future gates must not infer safety from display rows or fallback rows.

### Overlap 4 — freshness vs feed health

`core/runtime_snapshot_store.py` determines artifact freshness.

`core/feed_health_truth.py` determines feed health.

Reconciliation required:

- Fresh artifact does not always mean healthy feed.
- Healthy-looking feed payload in a stale artifact is not current truth.
- Future gates must require both artifact freshness and canonical feed health where appropriate.

### Overlap 5 — quote truth vs feed truth

`core/quote_truth.py` blocks fallback, subscription-failed, stale, missing, unknown, or price-mismatched quote evidence.

`core/feed_health_truth.py` blocks unsafe feed state.

Reconciliation required:

- Quote truth remains quote-source/quote-age policy.
- Feed truth remains runtime/symbol feed policy.
- Executable truth must require both when feed evidence exists.

## Known stale/fallback pathways to keep blocked

The feed roadmap must keep these paths non-executable unless explicitly proven live and safe:

- `rest_fallback`
- `recovered_fallback`
- `fallback_recovered`
- `fallback_estimated`
- `fallback`
- `quote_fallback`
- `close_fallback`
- `derived_fallback`
- `synthetic_offhours`
- `subscription_failed`
- `option_subscription_failed`
- `PRICE_MISMATCH`
- `STALE_OPTION_LTP`
- stale latest artifacts
- missing latest artifacts
- invalid latest artifacts
- websocket disconnected
- effective websocket disconnected
- option feed blocker not OK
- option tick age above max threshold
- missing option age when blocker or symbol feed says unsafe

## Current runtime consumers that must remain safe

Future FEED PRs must protect these consumers:

- Candidate executable truth
- Symbol execution safety
- Quote truth consumers
- Scoring truth consumers
- Top-opportunity truth reader boundary
- Dashboard snapshot reader
- Runtime status overlays
- Advisory/top-opportunity latest artifacts
- Review queue / operator-visible evidence
- Paper/live runtime mode separation

## Contract invariants locked by this PR

### Invariant 1 — canonical feed truth is read-only

`classify_feed_health_truth(...)` must remain read-only. It must not reconnect, resubscribe, mutate runtime state, write files, or call brokers.

### Invariant 2 — raw websocket state is not enough

`ws_connected=true` alone is not enough to declare feed sa-fe. Effective state, runtime state, symbol blockers, and tick age must be considered.

### Invariant 3 — per-symbol truth matters

A globally healthy feed does not automatically make every option candidate safe. Symbol-level option evidence must be checked for executable candidates.

### Invariant 4 — freshness and health are separate

Fresh artifacts are required for current visibility, but freshness alone does not prove feed health.

### Invariant 5 — fallback stays advisory

Fallback and recovered fallback data must never become executable feed evidence.

### Invariant 6 — dashboard is not the source of truth

Dashboard readers may display and normalize evidence. They must not define execution safety.

### Invariant 7 — future FEED gates must fail closed

Missing, invalid, stale, fallback, subscription-failed, or contradictory feed evidence must block executable/ranking paths unless a future scoped PR defines a safer narrower behavior.

## Immediate next PR after this audit

```text
PR-FEED-02R — Canonical Feed Health Contract Reconciliation
```

Required goals for PR-FEED-02R:

- Reconcile `core.runtime_stat-us_overlay.derive_feed_ok(...)` with `core.feed_health_truth.classify_feed_health_truth(...)`.
- Ensure one canonical feed decision can be consumed by runtime overlays and future gates.
- Preserve current behavior unless explicitly tested.
- Add negative tests for split-brain states:
  - raw websocket connected but effective websocket disconnected
  - feed_ok true but option blocker unsa-fe
  - global feed ok but symbol option ticks stale
  - fresh artifact but unhealthy feed payload
  - stale artifact with healthy-looking payload

## Out of scope for PR-FEED-01

- No hold gate implementation
- No warmup gate implementation
- No token freshness gate implementation
- No runtime snapshot writer changes
- No candidate pipeline suppression changes
- No ranking suppression changes
- No live/paper policy split changes
- No config hardening
- No websocket refactor
- No reconnect policy refactor
- No subscription budget refactor
- No dashboard UI changes
- No broker behavior

## Acceptance criteria

- Current feed owners are documented.
- Canonical feed-health truth owner is locked.
- Duplicate/overlapping logic is identified.
- Known stale/fallback pathways are listed.
- Runtime/dashboard/candidate consumers are identified.
- Next PR is explicitly PR-FEED-02R.
- This PR remains documentation-only.
- CI and repo gates are green.
