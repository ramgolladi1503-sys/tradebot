# V38 canonical launcher authority

Canonical read-only launcher:
`/Volumes/TradeBotData/tradebot-live-diskguard-successor-20260905/scripts/run_kite_read_only_observation_v1.py`

SHA-256: `8edd03cc13e74f6b1d1dbe01560136ee97e662ac61e26305051f27a8325fdd8b`

The launcher is observation-only. The runtime allowlist rejects order-capable
methods and emits `broker_write_authority=false`, `order_authority=false`,
`paper_authorized=false`, and `live_execution_authorized=false`. V37 storage,
failover, and evidence modules are reachable through the runtime imports.
