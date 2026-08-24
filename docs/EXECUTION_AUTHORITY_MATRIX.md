# Execution authority matrix

| Mode | Market data | Pipeline/UI | Persistence | Broker/order path |
|---|---|---|---|---|
| Normal LIVE | enabled | enabled | enabled | governed by existing gates |
| READ_ONLY_OBSERVATION | enabled | enabled | enabled | explicitly disabled |
| SIM/PAPER | source-dependent | enabled | enabled | no live broker authority |

Read-only mode sets `TRADEBOT_READ_ONLY=true`, `LIVE_AUDIT_ONLY=1`,
`ALLOW_LIVE_ORDERS=0`, `AUTO_TRADE=0`, `AUTO_ORDER=0`,
`LIVE_TRADING_ENABLED=false`, `PAPER_TRADING_ENABLED=false`, and all four
authority flags to `false`. Any downstream attempt to enable live trading
must fail its existing execution guards.
