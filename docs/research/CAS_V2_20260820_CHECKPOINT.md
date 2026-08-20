# CAS V2 — Aug 20, 2026 Checkpoint

This document is the authoritative handoff for the CAS V2 work completed on Aug 20, 2026. The purpose is to prevent rediscovery/re-archaeology on the next session.

## Governance

All work remains read-only / research-only:

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
```

No real broker orders are authorized.

## Frozen research rankings — DO NOT CHANGE

```text
SENSEX = H4
NIFTY = H5
BANKNIFTY = H5
```

The Aug20 prospective freeze session remains valid as outcome-blind research evidence.

## Aug20 prospective result

15:13 emitter outcome:

```text
SENSEX     NO_TRADE
NIFTY      NO_TRADE
BANKNIFTY  NO_TRADE
```

15:14 authoritative freeze artifacts:

```text
SENSEX H4      UP
NIFTY H5       FLAT
BANKNIFTY H5   FLAT
```

Important: the SENSEX 15:13 preliminary/emitter direction and the 15:14 freeze disagreed. The authoritative trading direction for the next design is the **15:14 freeze**, not the 15:13 preview.

The Aug20 outcome cannot be formally scored from the canonical post-cutoff corpus because the available `today/*_5minute.json` evidence ended at 11:05 IST. Do not retroactively promote Aug20 to CORRECT/WRONG from later screenshots.

## CAS-local implementation path

The working CAS research lane is external and independent of TradeBot production runtime:

```text
/Volumes/TradeBotData/cas-live-trial-20260820/
```

Do not clean, rebind, or reuse this path for TradeBot live-runtime work.

### Implemented CAS-local files

Under `paper-trades/`:

```text
shadow_emitter.py
post_cutoff_collector.py
test_repair.py
cas_v2_option_surface.py
test_cas_v2_option_surface.py
```

Under `freeze/surface/`:

```text
real_quote_adapter.py
```

There is also the pre-freeze CE+PE surface producer / sealed-snapshot path used by the deterministic harness. Preserve it; do not redesign it.

## Repairs completed

### 1. Pre-15:13 option plumbing

```text
PRE_1513_OPTION_RESOLUTION=PASS
PRE_1513_BID_ASK_CAPTURE=PASS
QUOTE_FRESHNESS_GATE=PASS
```

### 2. NO_TRADE causality

```text
NO_TRADE_REASON_COVERAGE=100%
NO_TRADE_CAUSAL_SNAPSHOT=PASS
```

Every future `NO_TRADE` artifact must carry a non-null causal reason.

### 3. Post-cutoff evidence

```text
POST_CUTOFF_CAPTURE=PASS
OUTCOME_BLINDNESS=PASS
FREEZE_SCORING_READY=PASS
OPTION_PNL_SCORING_READY=PASS
```

Post-cutoff capture is scoring-only and must never feed back into direction, strike, entry, stop, or targets.

### 4. V2 option-surface selector

```text
DIRECTION_TO_OPTION_SURFACE=PASS
MULTI_STRIKE_CANDIDATE_RANKING=PASS
STRIKE_SELECTION=PASS
EXPECTED_MOVE_MODEL=PASS
OPTION_REPRICING=PASS
STOP_MODEL=PASS
TARGET_MODEL=PASS
RR_GATE=PASS
ENTRY_BEST_ASK=PASS
QUOTE_FRESHNESS=PASS
DIRECTION_CONFIDENCE_AVAILABLE=PASS
STRIKE_CONFIDENCE_AVAILABLE=PASS
TARGET_CONFIDENCE_AVAILABLE=PASS
```

Mapping:

```text
15:14 freeze UP   -> rank CE surface -> BUY_CE if eligible
15:14 freeze DOWN -> rank PE surface -> BUY_PE if eligible
15:14 freeze FLAT -> NO_TRADE
```

The selected trade includes:

```text
symbol
strike
expiry
entry = fresh best ask
stop_loss
target_1
target_2
RR
confidence decomposition
```

### 5. 15:14 freeze wiring

```text
FREEZE_TO_V2_WIRING=PASS
PREVIEW_FREEZE_DIRECTION_CONFLICT_HANDLED=PASS
FROZEN_TRADE_ARTIFACT_SCHEMA=PASS
FROZEN_TRADE_DEADLINE_FAIL_CLOSED=PASS
OUTCOME_BLINDNESS=PASS
```

The design explicitly requires:

```text
15:13 preview = non-actionable
15:14 freeze  = authoritative
```

Example contract:

```text
15:13 preview DOWN
15:14 freeze UP
=> final trade follows UP
=> BUY_CE if the CE option-surface gates pass
```

### 6. Pre-freeze option surface

Deterministic harness proof:

```text
PRE_FREEZE_SURFACE_PRODUCER=PASS
BOTH_CE_PE_SURFACES_CAPTURED=PASS
SURFACE_SEALED_BEFORE_FREEZE=PASS
SURFACE_FRESHNESS_GATE=PASS
FREEZE_SURFACE_LOOKUP=PASS
POST_FREEZE_SURFACE_ACCESS=0
POST_CUTOFF_FEEDBACK_PATHS=0
OUTCOME_BLINDNESS=PASS
```

Latency measured in deterministic harness:

```text
SURFACE_LOAD_MS=1.95–3.08
SELECTOR_RUNTIME_MS=0.10–0.35
ARTIFACT_TO_NOTIFICATION_MS=0.75–0.96
FREEZE_TO_NOTIFICATION_MS=2.80–4.20
```

Independent notification wiring:

```text
SENSEX_INDEPENDENT_NOTIFICATION=PASS
NIFTY_INDEPENDENT_NOTIFICATION=PASS
BANKNIFTY_INDEPENDENT_NOTIFICATION=PASS
FROZEN_TRADE_VISIBLE_BY_1514=PASS  # harness only
```

## Real quote adapter

Approved source is the existing CAS Kite REST read-only GET path.

```text
REAL_QUOTE_SOURCE=Existing CAS Kite REST GET path in paper-trades/shadow_emitter.py
REAL_INSTRUMENT_SOURCE=Kite GET /instruments
AUTHENTICATION_REQUIRED=true
```

Adapter:

```text
/Volumes/TradeBotData/cas-live-trial-20260820/freeze/surface/real_quote_adapter.py
```

Safety:

```text
QUOTE_ADAPTER_READ_ONLY=PASS
ORDER_ENDPOINT_REACHABLE=false
```

Allowed endpoints are limited to read-only instrument/quote paths such as:

```text
/instruments
/quote
/quote/ltp
```

Missing Greeks remain `null`; they must not be fabricated.

## CURRENT BLOCKER — only remaining prospective proof

```text
REAL_SOURCE_CONNECTIVITY=NOT_ATTEMPTED
MARKET_QUOTE_PROSPECTIVE_PROOF=PENDING_NEXT_SESSION

SENSEX_CE_COUNT=NOT_OBSERVED
SENSEX_PE_COUNT=NOT_OBSERVED
NIFTY_CE_COUNT=NOT_OBSERVED
NIFTY_PE_COUNT=NOT_OBSERVED
BANKNIFTY_CE_COUNT=NOT_OBSERVED
BANKNIFTY_PE_COUNT=NOT_OBSERVED

REAL_QUOTE_FRESHNESS_GATE=PASS_STATIC_ONLY
PRE_FREEZE_REAL_SURFACE_READY=false
CAS_V2_RUNTIME_READY=false
FROZEN_TRADE_VISIBLE_BY_1514=NOT_PROVEN_REAL_RUNTIME
NEXT_CAS_SESSION_FULL_TRADE_READY=false
```

This is **not missing implementation**. It is missing real prospective market-session proof.

## Next-session required sequence — START HERE, DO NOT SEARCH AGAIN

Before the next CAS session:

1. Read this checkpoint first.
2. Confirm `/Volumes/TradeBotData/cas-live-trial-20260820/` is healthy and unchanged.
3. Confirm the frozen rankings remain H4/H5/H5.
4. Start the CAS read-only runtime with the existing real quote adapter.
5. Human operator performs any broker-authenticated start required by repository safety rules.
6. Prove real CE+PE quote surfaces for all three indices.
7. Keep both CE and PE surfaces ready before the direction is frozen.
8. Final refresh/seal must happen during approximately `15:13:45–15:13:59`.
9. At `15:14:00`, freeze the authoritative direction.
10. Immediately feed that frozen direction + sealed pre-freeze surface into V2.
11. Surface the full trade within seconds — do not wait until 15:15.
12. Continue post-cutoff capture to 15:30 for scoring only.

## User-facing 15:14 contract

The user must see one of these immediately after the freeze:

```text
BUY_CE
BUY_PE
NO_TRADE
```

For actionable trades display:

```text
INDEX
HYPOTHESIS
FREEZE_DIRECTION
ACTION
SYMBOL
STRIKE
EXPIRY
LOT_SIZE
ENTRY
STOP_LOSS
TARGET_1
TARGET_2
RR_TARGET_1
RR_TARGET_2
DIRECTION_CONFIDENCE
STRIKE_CONFIDENCE
TARGET_CONFIDENCE
OVERALL_TRADE_CONFIDENCE
QUOTE_TIMESTAMP
SURFACE_AGE_MS
NOTIFICATION_TIMESTAMP
SECONDS_TO_15:15
```

The user must not have to inspect logs or wait for a 15:15 completion report.

## Readiness promotion rule

Only set:

```text
NEXT_CAS_SESSION_FULL_TRADE_READY=true
```

when a real human-governed prospective session proves all of:

```text
real quote connectivity
real CE+PE candidate counts
fresh pre-freeze sealed surface
15:14 freeze consumes only pre-freeze data
V2 strike/entry/SL/target selection
immediate user notification before normal-market cutoff
post-cutoff evidence remains scoring-only
```

Do not promote readiness from harness-generated snapshots alone.

## Do not redo tomorrow

Do **not**:

- rediscover H4/H5;
- rerun Aug20 hypothesis ranking;
- reconstruct the Aug20 scheduler architecture from scratch;
- redesign strike/target selection;
- use the degraded Aug20 TradeBot observer as a dependency for CAS;
- alter CAS because of unrelated TradeBot live-runtime SQLite failures;
- claim Aug20 repaired V2 trades were generated prospectively.

Tomorrow starts from **real prospective quote connectivity + runtime proof**, not archaeology.
