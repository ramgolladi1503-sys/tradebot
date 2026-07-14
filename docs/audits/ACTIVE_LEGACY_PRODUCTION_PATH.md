# Active Legacy Production Path

**Audit Result:**
ACTIVE_PRODUCTION_PATH:
market-data dictionaries
→ TradeBuilder
→ Trade
→ cycle_ranked_candidates
→ blockers
→ ExecutionRouter

**Replay Adapter Verification:**
MISSING_PRODUCTION_REPLAY_ADAPTER
→ addressed by official provider

The legacy pipeline operates safely end-to-end on recorded schema-compliant events. Physical executions are explicitly skipped, fallbacks are disabled, and freshness bounds are honored via a deterministic replay clock.
