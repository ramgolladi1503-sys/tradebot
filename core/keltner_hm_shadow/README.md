# Keltner/Hilega Read-Only Shadow Observer

This package implements the frozen `keltner-hilega-initiation-confirmation-v1` research contract.

It is deliberately not a strategy module. It has no broker, order, ranking, risk or execution dependency.

Primary integration surfaces:

```python
TradeBotKeltnerHilegaShadowObserver
OhlcBufferFiveMinuteAdapter
adapt_tradebot_completed_five_minute_bar
```

Operational instructions: `docs/runbooks/keltner_hm_live_shadow_v1.md`.

Offline evidence: `research/keltner_hm_live_shadow_v1/OFFLINE_CERTIFICATION.md`.
