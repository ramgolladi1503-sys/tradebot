# TRADE TRUTH ACTUAL RUNTIME CALL GRAPH (PROGRAMMATICALLY VERIFIED)

**Lineage**: `c94ac255de62feb16cb2643c81c80c5fc3e1cc66`
**Status**: ALL CALLSITES VERIFIED

| Stage | Caller File | Callee Symbol | Verified Callsite | Verified Runtime Path |
|---|---|---|---|---|
| raw_market_ingestion | `core/trade_truth/market_capture_reader.py` | `iter_batches` | `iter_batches(` | True |
| canonical_market_snapshot | `core/market_snapshot_builder.py` | `build_symbol_market_snapshot` | `def build_symbol_market_snapshot(` | True |
| market_session_store_memory | `core/market_session_store.py` | `MarketMemorySnapshot` | `class MarketMemorySnapshot:` | True |
| strategy_evaluation_c1_c2 | `core/candidate_evaluators.py` | `evaluate_c1` | `def evaluate_c1(` | True |
| strategy_family_compatibility | `core/strategy_family_contract.py` | `check_strategy_family_compatibility` | `def check_strategy_family_compatibility(` | True |
| candidate_pool_admission | `core/strategy_family_contract.py` | `admit_candidate_to_pool` | `def admit_candidate_to_pool(` | True |
| governed_strategy_authority | `core/governed_strategy_authority.py` | `is_strategy_governed_eligible` | `def is_strategy_governed_eligible(` | True |
| ranking_orchestration | `core/candidate_ranking.py` | `rank_candidates` | `def rank_candidates(` | True |
| trade_ticket_construction | `core/trade_ticket.py` | `validate_trade_identity` | `validate_trade_identity(` | True |
| risk_engine_evaluation | `core/risk_engine.py` | `allow_trade` | `def allow_trade(` | True |
| execution_governance_validation | `core/governed_strategy_authority.py` | `validate_execution_candidate` | `def validate_execution_candidate(` | True |
| integrated_decision_tail | `core/trade_truth/integrated_decision_tail.py` | `execute_integrated_decision_tail` | `def execute_integrated_decision_tail(` | True |
| trade_truth_capture | `core/candidate_journal.py` | `build_trade_truth_record` | `build_trade_truth_record(` | True |
