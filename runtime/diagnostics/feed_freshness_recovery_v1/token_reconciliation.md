# Token Reconciliation

## Correct arithmetic

- Total desired feed tokens: 73
- Underlying/index tokens: 3
- Desired option tokens: 70
- Option tokens with post-subscribe ticks: 64
- Desired option tokens with no post-subscribe tick: 6

Per family: BANKNIFTY 26 desired / 24 tick-seen, NIFTY 26 / 24, SENSEX 18 / 16.

## Meaning of the historical fields

`option_feed_verification.subscribed_option_tokens_count_by_symbol` is populated by `_begin_option_feed_verification()` from `_option_runtime_state(tokens=desired)`. On connect, `desired` is assigned to `_LAST_TOKENS` immediately after synchronous `ws.subscribe()` and `ws.set_mode()` calls. There is no provider acknowledgement and no callback-confirmed applied registry in this path. The field therefore represents the requested/desired inventory, not verified active subscriptions.

The value 64 is also not callback-confirmed application truth. `_option_runtime_state()` counts tokens in `_LAST_TOKENS` that remain classifiable through `_TOKEN_TO_SYMBOL`; the same 64 tokens produced database ticks. The six-token difference is a zero-tick/classification gap. Historical evidence cannot distinguish broker-side omission, missing `MODE_FULL`, or valid but illiquid subscriptions.

Queued mutations in `core/feed/ws_mutation_queue.py` were not counted as applied by the queue helper. The startup connect path bypassed that helper entirely, so historical startup state had no queued/applied distinction.

## Exact zero-tick tokens

All six are the CE/PE pair at the outermost low strike selected for each family:

| Token | Underlying | Expiry | Strike | Type | Desired | Tick seen | Classification |
|---:|---|---|---:|---|---|---|---|
| 15116034 | BANKNIFTY | 2026-08-25 | 56300 | CE | yes | no | outermost-low CE, application unknown |
| 15116290 | BANKNIFTY | 2026-08-25 | 56300 | PE | yes | no | outermost-low PE, application unknown |
| 16816386 | NIFTY | 2026-08-04 | 23900 | CE | yes | no | outermost-low CE, application unknown |
| 16816642 | NIFTY | 2026-08-04 | 23900 | PE | yes | no | outermost-low PE, application unknown |
| 292810245 | SENSEX | 2026-07-30 | 77100 | CE | yes | no | outermost-low CE, application unknown |
| 293652741 | SENSEX | 2026-07-30 | 77100 | PE | yes | no | outermost-low PE, application unknown |

The strike/type mapping follows the resolver's deterministic `_option_distance_rank()` ordering and the frozen selected-strike inventory. Tradingsymbol text was not persisted, so it is intentionally not fabricated.

## Truth dimensions required after instrumentation

The runtime must separately report total feed, underlying, desired/eligible option, subscribe requested/queued/callback-applied, `MODE_FULL` requested/queued/callback-applied, tick-seen/fresh, and depth-seen/fresh counts. Until a new instrumented run exists, callback and generation columns are `UNKNOWN`, not inferred from tick presence.
