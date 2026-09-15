# TRADE TRUTH — PROSPECTIVE FULL LEVEL-C CAPTURE CALL GRAPH

## 1. Architectural Call Flow

```text
RAW MARKET EVENT (WebSocket / Stitched Ticks)
        │
        ▼ [1. RAW_MARKET_CAPTURE]
As-Of Tick Window (max_raw_tick_ts <= decision_ts)
        │
        ▼ [2. BAR_CAPTURE]
Closed 1-Minute OHLCV Bars (bar_end_ts <= decision_ts)
        │
        ▼ [3. MEMORY_CAPTURE]
MarketMemorySnapshot (rolling metrics, returns, volatility)
        │
        ├──► [4. FEATURE_CAPTURE]
        │       Decision features (returns bps, dist from open, range)
        │
        ├──► [5. REGIME_CAPTURE]
        │       Regime state, entropy, probabilities (or REGIME_STAGE_NOT_APPLICABLE)
        │
        ▼ [6. STRATEGY_EVALUATION]
C1 & C2 Evaluator Functions (qualified, scores, emissions)
        │
        ▼ [7. CANDIDATE_POOL]
Strategy Family Compatibility & Admission Gate (admit_candidate_to_pool)
        │
        ├──► [8. OPTION_SELECTION]
        │       Option strike/expiry resolution & Executable Quote Truth (ASK for BUY)
        │
        ▼ [9. RANKING]
Candidate Ranking (rank_candidates) with Opportunity Score Breakdown
        │
        ▼ [10. TRADE_CONSTRUCTION]
Trade Intent Object (if qualified; else TRADE_CONSTRUCTION=NOT_REACHED)
        │
        ▼ [11. RISK_STATE_EVALUATION]
RiskEngine Evaluation against captured read-only portfolio state
        │
        ▼ [12. GOVERNANCE_VALIDATION]
Governed Strategy Authority & Execution Validation
        │
        ▼ [13. FINAL_DECISION]
Integrated Decision Tail Verdict (ENTRY, NO_TRADE, BLOCKED, SKIPPED, ERROR)
        │
        ▼ [14. TRUTH_RECORD_STORE]
Immutable Append-Only Truth Record with SHA-256 Decision Hash & Chain Hash
```

## 2. Invariants Preserved
1. **Zero Forward Looking Data**: All inputs at every stage satisfy {	ext{input}} \le t_{	ext{decision}}$.
2. **Single Trace Lineage**: A single immutable `trace_id` spans raw ticks through to the final decision and truth record.
3. **Broker Safety**: `broker_write_authority=False`, `order_authority=False`, `BROKER_WRITE_CALLS=0`.
4. **Physical Output Isolation**: Replay input bundle contains strictly causal primitives; expected outputs are verified in a physically separate comparator.
