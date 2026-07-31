# PR #763 NIFTY Mode Lifecycle - 2026-07-31

## Status

`BLOCKED_BY_INDEX_FULL_DELIVERY_PROOF`

This report corrects the previous terminology. `subscribe()` and `set_mode()` local success are not broker acknowledgements. In this codebase they now mean:

- `subscription command local send succeeded`: `ws.subscribe(...)` returned without a local exception.
- `mode_command_dispatched`: a `ws.set_mode(...)` operation was attempted locally.
- `mode_command_local_send_succeeded`: `ws.set_mode(...)` returned without a local exception and the client-side `subscribed_tokens` map may have been updated.
- `mode_delivery_observed`: a later parsed callback proved the requested delivery mode.

Compatibility fields named `mode_request_succeeded*` remain in evidence temporarily. They are aliases for local send success, not broker acknowledgement.

## Failed Bounded Run Under Diagnosis

- Run ID: `unified-pr748-756-20260731-0fdf89effad5-live-3c74d646`
- Evidence root: `runtime/diagnostics/unified_live_validation_pr748_756_v1/unified-pr748-756-20260731-0fdf89effad5-live-3c74d646`
- Artifact manifest SHA256: `7640063abb74889e683015956923c47fc8173bef14e2a31ad4a6d773394e175b`
- Verdict: `UNIFIED_LIVE_EVIDENCE_PARTIAL_NOT_FORMAL_ACCEPTANCE`
- Blocker: `INDEX_FULL_PACKET_NOT_OBSERVED`

Observed NIFTY lifecycle from the prior run:

| Field | Value |
| --- | --- |
| token | `256265` |
| feed session | `kite-depth-1785482335` |
| reconnect generation | `0` |
| subscription requested epoch | `1785482333.274023` |
| subscribe local send succeeded epoch | `1785482333.274259` |
| mode local send succeeded epoch | `1785482333.274493` |
| first callback receipt epoch | `1785482333.529826` |
| latest callback receipt epoch | `1785482348.00314` |
| first source tick epoch | `1785482333.0` |
| latest source tick epoch | `1785482347.0` |
| first post-mode full receipt epoch | `null` |

The prior evidence proves callbacks arrived after the local `set_mode(FULL, [256265])` call returned. It does not prove whether a later subscribe reset the client-side NIFTY mode to quote, because command sequence instrumentation did not exist in that run.

## Code Path Instrumented

Every live callsite in `core.kite_depth_ws` that can contain NIFTY now records command lifecycle evidence:

| Callsite | Operation |
| --- | --- |
| `ensure_subscribed_tokens` | dynamic `subscribe()` then `set_mode(FULL)` |
| `_apply_subscription_delta` | rebalance/delta `subscribe()` then `set_mode(FULL)` |
| `_apply_subscription_delta:final_full` | final current-token `set_mode(FULL)` after delta application |
| `_resubscribe_full` | connect/reconnect replay `subscribe()` then `set_mode(FULL)` |

For token `256265`, each operation records:

- sequence number
- receipt epoch
- callsite
- operation
- socket generation
- feed session ID
- reconnect generation
- thread name
- token count
- requested mode
- client mode before and after
- local call result
- exception type
- reason

The active governed run writes these rows to:

`live/nifty_mode_lifecycle.jsonl`

## Final-Mode Invariant

For each active observation token, delivery evidence now requires:

1. subscription command was dispatched;
2. local FULL command succeeded after the latest subscription for the current generation;
3. no later subscribe or quote-mode command superseded it;
4. final current-generation local mode is `full`;
5. a post-mode callback was received;
6. parsed callback mode is `full`;
7. for NIFTY, `exchange_timestamp` is present.

The client-side mode map is still only local command-state evidence. It is not treated as broker delivery proof.

## Callback Truth

For token `256265`, evidence now records bounded counters:

- `post_mode_callback_count`
- `post_mode_quote_count`
- `post_mode_full_count`
- `first_post_mode_callback_epoch`
- `first_post_mode_quote_epoch`
- `first_post_mode_full_epoch`
- latest parsed mode via `latest_observation_packet.parsed_mode`
- `latest_observation_packet.has_exchange_timestamp`

For NIFTY:

- `mode=quote` without `exchange_timestamp` is quote delivery.
- `mode=full` with `exchange_timestamp` is full delivery.
- `ohlc` and `change` alone do not prove full delivery.

## Constituent Diagnostics

The PR #748 all-identity gate is unchanged. However, bridge diagnostics can now report constituent progress separately from the NIFTY index blocker:

- `constituent_full_delivery_count`
- `constituent_live_tick_count`
- `constituent_completed_bar_count`
- `minimum_40_coverage_status`

This prevents the first NIFTY rejection from hiding whether PR #749's 50-equity source is receiving ticks and forming bars.

## Regression Tests

Focused command:

```bash
pytest -q \
  tests/test_kite_depth_ws_observation_on_ticks.py \
  tests/test_kite_depth_ws_market_event_graph_lifecycle.py \
  tests/test_feed_subscription_generation.py \
  tests/test_market_event_graph_live_runtime_bridge.py \
  tests/test_market_event_graph_constituent_source.py \
  tests/test_unified_live_validation_pr748_756_v1.py
```

Result before bounded proof run:

```text
61 passed in 4.74s
```

