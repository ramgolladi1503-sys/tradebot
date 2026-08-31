# Read-Only Live Observer Authority — 2026-08-24

## Preservation identity

This document records the clean successor before credential rotation. It is a
preservation authority, not a merge authorization and not live-readiness proof.

```text
SUCCESSOR_WORKTREE=/private/tmp/tradebot-current-main-9c445aae
SUCCESSOR_BRANCH=ram/current-main-live-hardening
PRE_MANIFEST_AUTHORITY_SHA=d1169bb2bba61bff48d6e2d0bd7e76b29263a708
REMOTE_PRESERVATION_BRANCH=ops/read-only-live-observer-hardening-20260824
REMOTE_MAIN_AT_PRESERVATION=e8240c67e01f1abd7a59b1d1c2033f7e675cf81f
MERGE_BASE_WITH_REMOTE_MAIN=9c445aae0300ac19b5c6d34f456420df5035234d
COMMITS_AHEAD_OF_REMOTE_MAIN=17
COMMITS_BEHIND_REMOTE_MAIN=5
PROTECTED_CHECKOUT=/Users/madhuram/tradebot
PROTECTED_CHECKOUT_DIRTY=true
PROTECTED_CHECKOUT_TOUCHED=false
```

The final preservation SHA is the commit that adds this manifest and is
reported only after that commit is created and independently pushed/verified.

## Architecture components

The successor contains implementation-valid contracts for:

- a dedicated read-only observer composition root and hardened launcher;
- session manifest and bound `CONSUMERS.json` registry;
- pending feed, heartbeat, instrument-authority, and exit-gate artifacts;
- canonical SQLite read-only consumer access;
- immutable artifact hashing and evidence-gated session close seal;
- common read-only live candidates and provenance-preserving advisory ranking;
- causal `CAS_SW_RUNTIME_V2_1514` advisory-only freeze contract;
- isolated, exact-SHA sidecar policy and registry validation;
- advisory queue and lifecycle authority gates.

## Safety contract

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
BROKER_ORDER_CALLS=0
ORDERS_PLACED=0
ORDERS_MODIFIED=0
ORDERS_CANCELLED=0
```

No merge to `main` is authorized by this document. PR sidecars must remain
isolated, read-only, SHA-bound, PR-bound, and must not mutate the canonical
feed, subscriptions, SQLite, authentication, consumer state, or orders.

## Runtime truth status

```text
IMPLEMENTATION_VALID=true
LIVE_VERIFIED=false
CURRENT_SESSION_AUTH=NOT_PROVEN
CURRENT_SESSION_FEED=NOT_PROVEN
CURRENT_SESSION_PERSISTENCE=NOT_PROVEN
REGIME_RUNTIME=NOT_PROVEN
STRATEGY_EMISSION=NOT_PROVEN
OPTION_SURFACE=NOT_PROVEN
ADVISORY_QUEUE_RUNTIME=NOT_PROVEN
CAS_LIVE_VERIFIED=false
LIVE_OBSERVATION_E2E_READY=false
```

The focused read-only safety suite has passed 57 tests on the pre-manifest
authority. Those tests are implementation evidence only and do not substitute
for current-session broker, WebSocket, subscription, fresh-tick, persistence,
consumer, option-surface, or advisory evidence.

## Credential incident handoff

```text
EXPOSED_CREDENTIAL_TYPES=Kite API key + API secret/app secret
ACCESS_TOKEN_EXPOSURE=NOT_OBSERVED
ROTATION_REQUIRED=true
ROTATION_PERFORMED=false
```

Credential rotation is an operator action after preservation. Values must not
be pasted into chat, logs, Git, or evidence. The replacement binding must be
limited to the governed read-only LaunchAgent mechanism.

## Next-session operating sequence

1. Verify the preserved remote branch and final SHA from a clean checkout.
2. Rotate and rebind credentials through the operator-controlled process.
3. Validate metadata-only LaunchAgent startup and current-session read auth.
4. Prove instrument authority, one WebSocket owner, subscription parity, fresh
   ticks, and advancing canonical SQLite.
5. Verify session manifest, consumer registry, heartbeat, feed health, and
   persistence evidence.
6. Start canonical regime, strategy/CAS, candidate, option-surface,
   eligibility, ranking, advisory, monitoring, and evidence consumers.
7. Start only approved isolated sidecars and verify their SHA-bound evidence.
8. Keep `LIVE_OBSERVATION_E2E_READY=false` until every lifecycle gate is
   measured and passed; seal the session immutably after stop, flush, and
   no-respawn proof.
