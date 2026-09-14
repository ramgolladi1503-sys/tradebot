# Trade Truth — Actual Production Call Graph

**Lineage Boundary**: Canonical merged `main` (`c94ac255de62feb16cb2643c81c80c5fc3e1cc66`)  
**Scope**: 14 Verified Production Callables Across Market, Memory, Features, Regime, Strategy, Family, Pool, Governance, Ranking, Trade, Risk, and Truth Layers.

---

## 1. Verified Production Pipeline Stages

1. **Market Ingestion**: `core.market_snapshot_builder.build_market_snapshot`
2. **Canonical Snapshot**: `core.market_snapshot_schema.validate_market_snapshot`
3. **Session Memory**: `core.market_session_store.MarketSessionStore`
4. **Regime Entropy Gate**: `core.regime_entropy_gate.evaluate_regime_entropy_gate`
5. **Strategy Evaluation (C1)**: `core.candidate_evaluators.evaluate_c1`
6. **Strategy Evaluation (C2)**: `core.candidate_evaluators.evaluate_c2`
7. **Strategy Family Contract**: `core.strategy_family_contract.check_strategy_family_compatibility`
8. **Candidate Pool Admission**: `core.strategy_family_contract.admit_candidate_to_pool`
9. **Governed Strategy Authority**: `core.governed_strategy_authority.filter_governed_candidates`
10. **Ranking Orchestrator**: `core.ranking_orchestrator.build_ranked_opportunity_report`
11. **Trade Construction**: `core.trade_ticket.TradeTicket`
12. **Risk Engine**: `core.risk_engine.RiskEngine`
13. **Governance & Execution Validation**: `core.governed_strategy_authority.validate_execution_candidate`
14. **Trade Truth Capture**: `core.trade_truth.record_builder.build_trade_truth_record`

---

## 2. Invariants

- **Replay business logic duplication count**: 0
- **Mixed worktree imports**: 0
- **Execution authority**: None (strictly read-only)
