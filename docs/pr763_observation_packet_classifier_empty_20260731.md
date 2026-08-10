# PR #763 Observation Packet Classifier Empty Diagnostic - 2026-07-31

## Scope

Worktree: `/Users/madhuram/tradebot-unified-live-validation-pr748-756-v1`

Branch: `campaign/unified-live-validation-pr748-756-v1`

Starting HEAD: `6085282402d1c953eddbc23c22e37388712f715b`

Blocked live run: `unified-pr748-756-20260731-bfe922768f2a-live-0a227e84`

Blocked verdict: `OBSERVATION_UNION_ACTIVE_FULL_DELIVERY_NOT_OBSERVED_PACKET_CLASSIFIER_EMPTY`

This diagnostic preserves the prior evidence root unchanged. It does not alter the 50-constituent universe, minimum-40 coverage rule, feed gates, risk gates, execution gates, subscription budgets, or broker acknowledgement semantics.

## First Causal Break

The first proven causal break was inside `core.kite_depth_ws.on_ticks`.

The callback updated `_LAST_MSG_TS_BY_TOKEN[token]`, which caused lifecycle evidence to report live ticks for all observation identities, but `latest_observation_packet` was populated only later inside the accepted observation path. That later path was downstream of observation-plan context and shadow-bar acceptance. A registered observation-token callback could therefore be visible as a live tick while leaving `latest_observation_packet={}`.

That made the previous run ambiguous. It could prove callback freshness, but it could not prove whether the callback payload was quote, full, missing price, rejected by context, or lost before classification.

## Callback Path

The runtime callback path is:

```text
KiteTicker._on_message
-> KiteTicker._parse_binary
-> kws.on_ticks = on_ticks_current
-> on_ticks_current
-> core.kite_depth_ws.on_ticks
-> _LAST_MSG_TS_BY_TOKEN[token] timestamp update
-> _record_observation_callback_truth(...)
-> accepted observation shadow-bar gate
-> market_event_graph_live_ohlc_buffer.record_live_source_shadow_tick(...)
```

The repair records raw observation callback truth at the same boundary that records token freshness:

```text
_LAST_MSG_TS_BY_TOKEN[int(token_int)] = float(freshness_tick_epoch)
_record_observation_callback_truth(...)
```

This is intentionally before `last_price`, bar publication, full-payload acceptance, and Market Event Graph interval gates.

## Raw Versus Accepted Truth

Raw callback truth now records for registered observation tokens even when the packet is not accepted for bars:

- `callback_seen`
- `registered_observation_callback_count`
- `raw_packet_kind`
- `raw_full_payload`
- `tick_keys`
- `has_last_price`
- `plan_enabled`
- `token_in_observation_registry`
- `token_in_active_plan`
- `feed_session_matches`
- `reconnect_generation_matches`
- `subscription_send_recorded`
- `mode_full_is_final_local_command`
- `post_mode_callback`
- `accepted_for_shadow_bar`
- `rejection_reason`
- `state_identity`

Accepted observation truth remains gated by the existing live-source readiness, feed session, reconnect generation, subscription acknowledgement, final local full-mode command, post-mode callback, and bar-price requirements. No acceptance rule was weakened.

## Rejection Classes

The raw callback recorder emits explicit rejection classes:

- `CALLBACK_SEEN_PLAN_DISABLED`
- `CALLBACK_SEEN_SESSION_MISMATCH`
- `CALLBACK_SEEN_GENERATION_MISMATCH`
- `CALLBACK_SEEN_SUBSCRIPTION_UNPROVEN`
- `CALLBACK_SEEN_MODE_NOT_FINAL_FULL`
- `CALLBACK_SEEN_QUOTE_PACKET`
- `CALLBACK_SEEN_FULL_PACKET`

`CALLBACK_SEEN_FULL_PACKET` means the raw packet classifier saw a full payload in an otherwise current observation context. It does not by itself imply order authority, broker execution, or formal live acceptance.

## Module And State Identity

Local duplicate-module check:

```text
ws_module_name core.kite_depth_ws
ws_module_file /Users/madhuram/tradebot-unified-live-validation-pr748-756-v1/core/kite_depth_ws.py
engine_ws_is_ws True
```

Captured state identity sample:

```text
module_name=core.kite_depth_ws
module_file=/Users/madhuram/tradebot-unified-live-validation-pr748-756-v1/core/kite_depth_ws.py
last_msg_state_id=<runtime id>
latest_observation_packet_state_id=<runtime id>
```

The bounded live diagnostic must compare the runtime `state_identity` embedded in `latest_observation_packet` with the lifecycle evidence for the same process. If `registered_observation_callback_count > 0` and `latest_observation_packet` remains empty for the same token, that is a new state-identity or evidence serialization defect.

## Regression Tests

Focused tests added in `tests/test_kite_depth_ws_observation_on_ticks.py`:

- registered callback with no `last_price` still records packet truth;
- packet truth is recorded at the same boundary as callback timestamp freshness;
- rejected reconnect-generation context still records raw callback truth and does not publish bars;
- equity full callback records raw full packet truth without requiring bar publication;
- `core.depth_subscription_engine` and `core.kite_depth_ws` use the same module object and callback recorder.

Passing focused command:

```bash
pytest -q tests/test_kite_depth_ws_observation_on_ticks.py
```

Result:

```text
27 passed
```

## Bounded Live Outcome Rules

The next governed proof must be 5-10 minutes maximum.

Outcome A: raw callback truth is populated, full payloads are observed, completed constituent bars are published, and the first MEG result appears. A longer same-day run can proceed only after this.

Outcome B: raw callback truth is populated but packets remain quote or context-rejected. Classify the exact rejection; do not claim formal acceptance.

Outcome C: lifecycle live ticks continue but raw callback truth remains empty. Classify as a callback/state identity defect, not broker full-delivery failure.

No evidence from `unified-pr748-756-20260731-bfe922768f2a-live-0a227e84` may be combined with any post-fix run.
