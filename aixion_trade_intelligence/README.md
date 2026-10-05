# Aixion Trade Intelligence Evidence Kernel

This package is a read-only evidence, replay, lineage, and causal outcome sidecar for TradeBot.

It does not import broker order routers, mutate strategies, alter ranking, change risk, or place orders.

## Authoritative flow

```text
TradeBot candidate lineage
+ Upstox quote capture
→ canonical append-only events
→ deterministic replay
→ session-quality manifest
→ candidate lineage
→ causal underlying and option outcomes
→ offline pipeline certification
→ JSON and Markdown report
```

## Commands

```bash
PYTHONPATH=. python scripts/generate_offline_fixture.py --output /tmp/aixion_events.jsonl
PYTHONPATH=. python -m aixion_trade_intelligence certify \
  --events /tmp/aixion_events.jsonl \
  --output-dir /tmp/aixion_report
```

The `PIPELINE_OFFLINE_CERTIFIED` verdict proves only evidence-pipeline integrity. It never certifies strategy edge or profitability.
