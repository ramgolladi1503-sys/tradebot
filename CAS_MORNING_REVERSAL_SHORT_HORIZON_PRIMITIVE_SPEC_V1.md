# CAS Morning Reversal Short-Horizon Primitive Specification V1

SPEC_ID=CAS_MORNING_REVERSAL_SHORT_HORIZON_PRIMITIVE_SPEC_V1  
AUTHORITY_CLASS=MIXED  
HISTORICAL_AUTHORITY_COMPONENTS=V7_PROSPECTIVE_ADMISSION_CONTRACT; repository strategy registry; CAS advisory evaluator  
INDEPENDENTLY_DERIVED_OPERATIONAL_COMPONENTS=price last_price; typed timestamp admission; additive primitive record schema  
SOURCE_LIVE_RELEASE_SHA=57e8717af1a2ddf06d443459b0f9797ea3b3f53f  
SPEC_STATUS=FROZEN  
IMPLEMENTATION_STATUS=NOT_IMPLEMENTED

## Economic contract

`strategy_id=CAS_MORNING_REVERSAL_SHORT_HORIZON_V1` (repository verified). Targets are `09:15:00.000` and `10:00:00.000` Asia/Kolkata (recovered V7 authority). `morning_return=Price(10:00)/Price(09:15)-1` (recovered V7/CAS evaluator). Positive maps to `DOWN`, negative to `UP`, exact zero to `NO_SIGNAL`. Decision boundary is `15:14:00` Asia/Kolkata. Output is advisory-only.

## Price and timestamp

Price is `last_price` from `core/tick_store.py`, an independently derived operational choice. It must be finite and positive and come from the same normalized tick event as timestamp provenance. No midpoint, option price, interpolation, carry-forward, zero-fill, or completed future-containing bar is permitted.

Timestamp fields are `timestamp_epoch`, `timestamp_authority`, `timestamp_source_field`, `source_timestamp_epoch`, `receive_timestamp_epoch`, and `timestamp_fallback_used`. Eligible authority is `EXCHANGE_TIMESTAMP`; `GOVERNED_RECEIVE_TIMESTAMP`, `LOCAL_FALLBACK_TIMESTAMP`, and `UNKNOWN` are ineligible. The selected timestamp must be the validated exchange value, with receive time retained for audit. Missing/invalid provenance blocks capture; no retrospective inference is allowed.

## Selection and state

For each target independently, select the first eligible authoritative underlying tick with selected timestamp >= target and lateness <= 2000 ms. Before target: `PENDING`. First valid tick in window: terminal `CAPTURED`. Window expiry without valid tick: terminal `MISSED`. Authority, identity, or safety violation: terminal `BLOCKED`. CAPTURED, MISSED, and BLOCKED cannot be overwritten or retroactively changed.

## Primitive record

Required fields: `schema_version`, `strategy_id`, `session_id`, `source_sha`, `underlying_symbol`, `underlying_token`, `primitive_name`, `target_timestamp_ist`, `capture_status`, `capture_timestamp_ist`, `price`, `price_field`, `price_source`, all six timestamp fields above, `lateness_ms`, `freshness_pass`, `captured_live_prospectively`, `immutable`, `admissible_for_prospective_campaign`, `created_at_ist`, `record_sha256`. Null remains null; no missing value becomes zero.

## Underlying and admission

Authorized underlying is `NIFTY`; its token is resolved from the same-day canonical instrument authority and must match the runtime's authoritative mapping (no stale hardcoded token). Both primitives must be CAPTURED prospectively, eligible, fresh, valid, same session/source SHA, independently verifiable, and complete before 15:14. Risk halt may block advisory readiness but cannot rewrite capture truth. Historical replay, fixture, late reconnect, or post-close reconstruction can never set prospective admission.

## Persistence and inputs

Primitive store: governed session evidence artifact `cas_short_horizon_primitives_<session_id>.json`, atomically create-only, keyed by `(session_id, source_sha, underlying_symbol, primitive_name)`, with manifest hash. Restart reads the original record; it never recaptures or overwrites it. `cas_short_horizon_inputs` is a cycle-bound object containing strategy/session/source/cycle identity, immutable 09:15 and 10:00 primitive references and prices, `morning_return`, `signal_direction`, and capture/admission metadata. `run_consumer_cycle()` must receive it only after both primitives verify.

## Independent validation

An independent verifier must validate spec hash, schema, identity, dynamic token mapping, price/timestamp same-event binding, authority eligibility, target/lateness, finite positive prices, capture-once/immutability, prospective admission, manifest integrity, input schema, and cycle binding. Producer status fields are not trusted.

## Safety

`broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_execution_authorized=false`, `execution_status=advisory_only`. This specification authorizes only a future isolated producer implementation; it does not authorize merge, deployment, live restart, broker writes, or orders.
