# Aixion Trade Intelligence V1

## Current deliverable

This branch implements the first production-safe slice of the intelligence sidecar:

```text
TradeBot/read-only fixture events
→ canonical validation
→ idempotent append-only evidence log
→ deterministic replay
→ session-quality manifest
→ candidate-lineage completeness
→ offline report bundle
```

## What is derived rather than hardcoded

- latency percentiles are derived from event timestamps;
- starvation/event gaps are derived from ordered event times;
- sequence loss is derived from producer sequence numbers;
- instrument and strategy coverage are derived from observed identities;
- candidate-funnel counts are derived from lifecycle events;
- session validity is based on required lifecycle, source quality and evidence continuity;
- no profitability, market-edge, score or trading threshold is embedded.

## Offline command

```bash
python scripts/run_aixion_trade_intelligence_offline.py \
  --event-log /path/to/<session>/events.jsonl \
  --output-dir runtime/aixion_trade_intelligence/<session>
```

## Certification boundary

The current slice can certify:

```text
canonical event validity
payload integrity
idempotent persistence
deterministic replay
single-session integrity
lifecycle completeness
producer-sequence continuity
data-quality-state integrity
candidate-to-outcome lineage completeness
```

It cannot certify:

```text
strategy edge
profitability
live option fills
capacity
holdout performance
CAS direction
production order readiness
```

## Live-session boundary

Tomorrow's live check is a canary, not live-trading certification.

Required evidence before enabling a read-only publisher in the live runtime:

1. focused offline workflow green;
2. analytics package contains no broker/order authority;
3. publisher failure is non-blocking to TradeBot;
4. output directory is writable and has adequate disk space;
5. session ID and schema version are visible;
6. one controlled paper/shadow session is captured;
7. event counts, sequence gaps and lifecycle are reviewed after close.

No order authority is added by this branch.
