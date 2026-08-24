# Canonical Read-Only Live Pipeline Architecture

Status: implementation work in progress. This document is a source-map and
classification record, not live-session proof.

## Authority and safety boundary

- Source branch: `ops/read-only-live-observer-bootstrap-20260824`
- Source SHA at mapping time: `b73d84c5dcc3f10d79f8f1e177fb319de576ea13`
- Worktree: `/Volumes/TradeBotData/tradebot-readonly-live-authority-0916a95f`
- Protected checkout: `/Users/madhuram/tradebot` (dirty and excluded)
- Broker write authority: `false`
- Order authority: `false`
- Paper authorization: `false`
- Live execution authorization: `false`
- Broker order calls: `0` required; any attempted call is a hard failure

No implementation or contract test in this document proves current-session
authentication, feed freshness, persistence advancement, or end-to-end health.

## Canonical runtime graph

```text
current-session auth
  -> read-only observer
      -> current instrument authority
      -> canonical live SQLite / immutable artifacts
          -> regime consumer
          -> strategy registry consumers
          -> CAS V2 consumer
          -> candidate pool
              -> option surface
              -> eligibility
              -> ranking
              -> advisory queue
                  -> UI/read model
          -> monitoring / evidence
      -> isolated PR validation sidecars
```

The observer is the only canonical feed owner. Sidecars consume immutable
artifacts or explicitly declared replay inputs and cannot own the feed,
mutate the canonical database, or mutate the main session.

## Existing component classification

| Component | Decision | Reason / boundary |
|---|---|---|
| `core/auth.py` governed Kite client | KEEP | Existing authentication boundary; only read-only methods may be called. |
| `core/read_only_instrument_authority.py` | KEEP | Current instrument master acquisition and hash authority. |
| `core/kite_depth_ws.py` | KEEP | Canonical WebSocket/feed mechanism; one owner only. |
| `core/kite_read_only_observation_runtime.py` | ABSORB | Composition root for the permanent pipeline entrypoint. |
| `core/tick_store.py`, `core/depth_store.py`, `core/feed/runtime_store.py` | ABSORB | Canonical persistence primitives; health must be measured at runtime. |
| `core/live_session_manifest.py` | ABSORB | Session identity and fail-closed authority contract. |
| `core/live_consumer_contract.py` | ABSORB | Shared consumer registry and topology. |
| `core/live_runtime_artifacts.py` | ABSORB | Truthful startup and pending-state artifacts. |
| `core/live_candidate_contract.py` | ABSORB | Common strategy/CAS candidate boundary. |
| `core/cas_v2_consumer_contract.py` | ABSORB | CAS must emit through the common candidate/advisory path. |
| `core/live_ranking_contract.py` | ABSORB | Advisory-only ranking boundary. |
| `core/advisory_queue_contract.py` | ABSORB | Shared append-only advisory sink. |
| `core/live_sidecar_contract.py` | ABSORB | Exact-SHA and failure-isolated sidecar policy. |
| `core/read_only_live_evidence.py` | ABSORB | Immutable evidence helpers; no execution authority. |
| `core/regime*.py` family | SUPERSEDE as direct launch targets | Historical/analysis implementations require an explicit canonical adapter; none may independently own live feed state. |
| `core/candidate_*.py` family | SUPERSEDE as direct launch targets | Existing generators and ranking helpers are not canonical until registered and adapted to `LiveCandidate`. |
| `core/option_*.py` family | SUPERSEDE as direct launch targets | Option analysis is downstream of current-session candidate and option-surface truth; no order path. |
| `core/ranking_*.py` family | SUPERSEDE as direct launch targets | Historical/orchestrator paths cannot bypass the shared ranking/advisory contracts. |
| `scripts/run_live.sh` | SUPERSEDE | Must not be the canonical read-only daily entrypoint while it can select overlapping runtime paths. |
| historical observer wrappers and old LaunchAgent paths | RETIRE after migration | Preserve as historical evidence until the new runtime is certified; do not run concurrently. |
| research/backtest/replay scripts | RETIRE from live authority | May remain offline research tools; never count as current-session proof. |

## Required runtime stages

The permanent entrypoint must emit explicit states, in order:

`SOURCE_READY -> AUTH_READY -> INSTRUMENT_AUTHORITY_READY -> FEED_READY -> PERSISTENCE_READY -> REGIME_READY -> STRATEGIES_READY -> CAS_READY -> CANDIDATES_READY -> OPTION_SURFACE_READY -> ELIGIBILITY_READY -> RANKING_READY -> ADVISORY_READY -> SIDECARS_READY -> E2E_READY`

Any missing, stale, divergent, or unmeasured stage is `BLOCKED` or `PENDING`.
Unit tests and static contracts cannot advance a current-session stage.

## Promotion ladder

1. `CANONICAL_READ_ONLY_LIVE_PIPELINE_IMPLEMENTED`
2. `CANONICAL_READ_ONLY_LIVE_PIPELINE_RUNTIME_VALIDATED`
3. `CANONICAL_READ_ONLY_LIVE_PIPELINE_E2E_CERTIFIED`
4. `CANONICAL_READ_ONLY_LIVE_PIPELINE_PROMOTED_TO_MAIN`

The next stage is not implied by the previous stage. Main remains unchanged
until real-session E2E evidence, independent exit-artifact verification, and
remote exact-SHA preservation all pass.

