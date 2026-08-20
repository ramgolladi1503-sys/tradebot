# PR 814 Agent Review Evidence — H1 Shadow Adapters V1

## Agent Work Contract

Objective: add an H1-specific, no-order, offline-certifiable shadow adapter path for `H1_TRAPPED_PUSH_SNAPBACK` on branch `research/h1-shadow-adapters-v1` targeting `research/strategy-certification-kernel-v0`.

Allowed scope:

- add H1 raw Kite CSV normalization into the hardened V19 completed-bar schema;
- add a daily H1 shadow adapter runner that calls the existing validator and observer;
- add a shadow-only H1 strategy module that emits non-routeable `BUY_PUT_SHADOW` measurement intents;
- register only `H1_TRAPPED_PUSH_SNAPBACK_SHADOW` as a shadow trade-intent strategy;
- add H1-specific tests and offline certification script.

Prohibited scope:

- no live orders;
- no paper orders;
- no broker writes;
- no Kite/Upstox API writes;
- no change to the frozen H1 predicate;
- no qualification, supersession, deletion, or behavior change for existing strategies.

## Scope Guard

This PR is intentionally narrow. It leaves existing TradeBot strategy entries alone and adds only one new shadow strategy entry:

```text
H1_TRAPPED_PUSH_SNAPBACK_SHADOW
```

The existing strategies are not requalified, promoted, deleted, or superseded by this PR.

## High-Risk Path Review

High-risk files changed:

- `strategies/strategy_registry.py`
- `strategies/shadow/h1_trapped_push_snapback.py`

Review outcome:

- `strategies/strategy_registry.py` adds one H1-only shadow entry and does not alter existing entries.
- H1 is registered as `shadow_trade_intent_strategy`, not execution strategy.
- `blocked_reason` explicitly preserves the no-broker/no-paper/no-live boundary.
- The H1 strategy module emits only shadow intent records and intentionally excludes routeable execution fields such as `tradingsymbol`, `instrument_token`, `quantity`, `order_type`, `product_type`, broker order id, and exchange order id.
- Authority flags remain false in emitted records.

## Grill Me Review

Attack questions:

1. Did the PR change the frozen H1 predicate?
   - Expected answer: no. Predicate text remains `(range_bps[t-1] > 12.0) & (upper_wick_bps[t-1] > 4.0) & (body_bps[t] < -2.0)`.
2. Does it emit real orders or routeable paper orders?
   - Expected answer: no. It emits `SHADOW_TRADE_INTENT_ONLY_NO_ORDER` records only.
3. Does it qualify old TradeBot strategies?
   - Expected answer: no. Existing strategies remain as they were.
4. Does it prove execution viability?
   - Expected answer: no.
5. Does it prove structural edge certification?
   - Expected answer: no.

## Hermes Review

Message to future operator:

Run H1 in this order only:

```bash
python -m pytest -q tests/test_h1_shadow_adapter.py
python scripts/research/hypothesis_factory/certify_h1_shadow_offline.py
python scripts/research/hypothesis_factory/run_h1_shadow_daily_adapter.py \
  --observation-date YYYY-MM-DD \
  --raw-kite-csv <raw_kite_csv> \
  --evidence-commit <current_h1_evidence_commit>
```

Do not use this branch to enable paper trading or live trading.

## GSD Review

Get-stuff-done checklist:

- [x] H1 adapter code added.
- [x] H1 no-order daily runner added.
- [x] H1 shadow trade-intent strategy added.
- [x] H1 registry entry added.
- [x] H1 focused tests added.
- [x] H1 offline certification script added.
- [ ] CI green.
- [ ] Offline certification output committed only after repository-native execution if required by reviewer.

## QA / Safety Review

Safety invariants required before merge:

```text
orders_created = 0
broker_writes_created = 0
paper_authorized = false
live_authorized = false
order_authority = false
broker_write_authority = false
routeable_order = false
predicate_changed = false
```

Focused commands:

```bash
python -m pytest -q tests/test_h1_shadow_adapter.py
python scripts/research/hypothesis_factory/certify_h1_shadow_offline.py
```

The offline certification must return `H1_SHADOW_OFFLINE_CERTIFICATION_PASS` before merge consideration.

## Acceptance Proof

Acceptance requires all of the following:

- PR CI green;
- focused H1 tests pass;
- offline certification gate passes;
- no routeable order fields are emitted;
- no existing strategy is marked as superseded or newly qualified;
- H1 remains shadow-only.

## Runtime Proof Required After Merge

After merge, runtime proof is still required. The first post-merge runtime proof should be a no-order H1 shadow session using completed NIFTY 5-minute bars.

It must log:

- completed-bar input audit;
- observer manifest;
- shadow trade-intent log;
- zero orders;
- zero broker writes;
- no paper/live authority.

This post-merge runtime proof is not allowed to claim paper readiness, live readiness, execution viability, or structural edge certification.

## What This PR Does Not Prove

This PR does not prove:

- prospective support;
- execution viability;
- tradable options edge;
- structural edge certification;
- paper readiness;
- live readiness;
- profitability after costs, spread, slippage, impact, taxes, or fills.

It only adds an H1 offline/shadow adapter and trade-intent measurement path.

## Human Approval

Human approval is required before:

- merging this PR;
- treating H1 shadow intents as paper trades;
- enabling any route to TradeBuilder, risk engine, execution router, broker adapter, Kite, or Upstox;
- using this H1 candidate as a user-facing signal.

Current approval state:

```text
merge_authorized = false
paper_authorized = false
live_authorized = false
order_authority = false
broker_write_authority = false
```
