# Feed Truth Gap Map

## What the code does well

| Truth Layer | Behavior |
| --- | --- |
| Option LTP freshness | Explicitly tracked and can block live candidates |
| Underlying tick freshness | Tracked separately from websocket connectivity |
| Bid/ask spread | Used in liquidity and scoring |
| Depth availability | Used as a real quality signal |
| Fallback / recovered truth | Kept distinguishable from real truth |
| Market session state | Modeled explicitly |

## Where truth can still be softened

| Softening Path | Risk |
| --- | --- |
| Inferred fallback or recovered fields | Can make the system look healthier than it is |
| Synthetic quote sources | Useful for diagnostics, but not executable truth |
| Advisory/watchlist rows | Can be misread as tradable if labels are sloppy |
| Runtime summaries that only show connection health | Websocket connected is not the same as quote fresh |

## Feed truth blockers seen in live evidence

| Evidence | Meaning |
| --- | --- |
| `FEED_LTP_STALE` | The live per-symbol option quote age is too old |
| `STALE_OPTION_TICK` | Option tick freshness fails the execution filter |
| `non_live_option_chain` | The chain is not trustworthy enough for execution |
| `contract_resolution_fallback_blocked` | Fallback contract mapping is intentionally non-executable |

## Required invariant

Fallback, recovered, stale, advisory, or degraded data must stay display/debug/watchlist only.

That invariant is already mostly respected in the code, but it still needs to be enforced and labeled more clearly in the reports so humans do not confuse “visible” with “executable.”
