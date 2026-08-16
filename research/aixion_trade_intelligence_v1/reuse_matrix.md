# Aixion Trade Intelligence V1 Reuse Matrix

| Capability | Existing authority | V1 action | Replacement? |
|---|---|---|---|
| Candidate funnel | `core/candidate_lineage_ledger.py` | Tail and adapt existing JSONL | No |
| Feed truth | `core/feed_truth_contract.py` and runtime snapshots | Preserve as source payload in future adapters | No |
| Execution truth | existing execution-truth owners | Preserve; no decision override | No |
| TradeBuilder mapping | `strategies/trade_builder.py` | Observe emitted lineage only | No |
| Upstox market capture | existing daily Parquet capture | Read-only import of exact rows | No |
| Slippage/fill models | existing core modules | Not claimed calibrated by V1 | No |
| Strategy decay | existing core modules | Deferred evidence adapter | No |
| Confidence calibration | existing analytics modules | Deferred evidence adapter | No |
| Replay engine | existing option replay is strategy authority | V1 adds canonical event replay, not option simulation replacement | No |
| Evidence RAG | `core/tradebot_rag.py` | Reuse repository evidence RAG | No |
| CAS research | PR/research evidence | Deferred read-only adapter | No |
| Broker/order routing | existing runtime | Forbidden scope | No |
| Risk engine | existing runtime | Forbidden mutation; observe later | No |

## New capability justified

The missing capability is a canonical cross-owner evidence contract that joins candidate decisions to exact market evidence and causal outcomes. Existing components remain authoritative in their domains.
