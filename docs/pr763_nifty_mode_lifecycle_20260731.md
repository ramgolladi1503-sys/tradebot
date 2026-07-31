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

After the first short proof exposed a disabled observation plan, an additional regression was added for `build_subscription_tokens(...)` activating the PR #749 observation plan and merging all 51 observation identities into `_LAST_DESIRED_TOKENS`.

Updated focused result:

```text
62 passed in 6.40s
```

After the second short proof showed the live process was patched through `core.depth_subscription_engine`, the same activation invariant was added to that engine and covered directly.

Updated focused result:

```text
63 passed in 5.47s
```

## Short Proof Run 1

- Run ID: `unified-pr748-756-20260731-fd1a9da3a6a7-live-0ce9ea51`
- Campaign commit: `af4f66768`
- Artifact manifest SHA256: `67fc1347a8fbce6e3232f86517d59c0fc562cf284d4f222a694cedd43f604dc1`
- Sealed: `true`
- Verdict: `OBSERVATION_PLAN_DISABLED_MODE_LIFECYCLE_PARTIAL`

NIFTY command sequence recorded:

| Sequence | Callsite | Operation | Result | Client mode before | Client mode after | Token count |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `_resubscribe_full` | `subscribe` | `dispatched` | `null` | `null` | 73 |
| 2 | `_resubscribe_full` | `subscribe` | `succeeded` | `null` | `quote` | 73 |
| 3 | `_resubscribe_full` | `set_mode` | `dispatched` | `quote` | `null` | 73 |
| 4 | `_resubscribe_full` | `set_mode` | `succeeded` | `quote` | `full` | 73 |

This proves no later NIFTY subscribe reset the local mode during that short run. It also proves the subscribed set was the normal 73-token production set, not the PR #749 observation union.

First causal break in that run:

```text
MARKET_EVENT_GRAPH_LIVE_SOURCE_ENABLE=true
-> authoritative universe resolvable by bridge
-> WebSocket observation plan state remained DISABLED
-> 51 observation identities not merged into _LAST_DESIRED_TOKENS
-> observation-specific callback classifier did not stamp latest_observation_packet
-> constituent diagnostic progress stayed hidden behind INDEX_FULL_PACKET_NOT_OBSERVED
```

The fix now activates the observation plan inside `build_subscription_tokens(...)` after production-token pruning/budgeting and before desired tokens are frozen. The union is only applied when the existing configured budget accepts the 51-token observation universe.

## Short Proof Run 2

- Run ID: `unified-pr748-756-20260731-65fbbf0292bb-live-1b68ac35`
- Campaign commit: `0cc35b62b`
- Artifact manifest SHA256: `e6732027f8e90d8ee03f937753a44ae487a59946459113aac012c55d1158cfd7`
- Sealed: `true`
- Verdict: `OBSERVATION_PLAN_STILL_DISABLED_IN_RUNTIME_ENTRYPOINT`

NIFTY command sequence again showed only the production 73-token subscription:

```text
subscribe 73 tokens
set_mode FULL 73 tokens
no later NIFTY subscribe
final local NIFTY mode full
```

The observation plan state was still:

```text
enabled=false
verdict=DISABLED
observation_tokens=[]
final_union_tokens=[]
```

This proved the first activation fix was placed in `core.kite_depth_ws.build_subscription_tokens(...)`, but the live runtime path was using the `core.depth_subscription_engine` patched builder. The engine now performs the same observation-union activation before freezing `_LAST_DESIRED_TOKENS`.
