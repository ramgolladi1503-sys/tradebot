# Failed Restart Inventory

Source evidence was preserved at:
`/Users/madhuram/tradebot/.runtime/logs/depth_ws_watchdog.log` and
`/Users/madhuram/tradebot/.runtime/logs/feed_restart_guard.jsonl`.

The temporary supervisor performed 12 bounded process restarts. Each fresh
process reached WebSocket connected, subscribed 73 tokens, passed option
verification for BANKNIFTY/NIFTY/SENSEX, and emitted immediate `FEED_TICK`
activity. Each attempt later entered a stale window and reproduced
`partial_recovery`; subsequent ticks did not clear the local terminal truth.

No order, fill, broker-write, strategy, risk, subscription-universe, or depth
persistence change was made by the supervisor. The prior evidence remains in
its original location and was read only.
