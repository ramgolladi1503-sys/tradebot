# Replay-to-Live Normalization Bridge

This document proves the exact parity and shared function calls between live mode and the replay vertical slice.

| Stage | Live function | Replay function | Same implementation? |
| :--- | :--- | :--- | :--- |
| raw event intake | `fetch_live_market_data` (`core/market_data.py`) | script CLI parsing (`scripts/run_nifty_vertical_slice_replay.py`) | No, replay ingests from disk but preserves format |
| normalization | `_snapshot_symbol_payload` (`core/orchestrator.py`) | `build_market_snapshot_from_raw_tick` (`core/market_snapshot_builder.py`) | No, pure adapter extracted for replay purity |
| market snapshot | `build_symbol_market_snapshot` (`core/market_snapshot_builder.py`) | `build_symbol_market_snapshot` (`core/market_snapshot_builder.py`) | Yes |
| StrategyContext | `_strategy_context_from_market_symbol` (`core/runtime_snapshot_producer.py`) | `_strategy_context_from_market_symbol` (`core/runtime_snapshot_producer.py`) | Yes |
| strategy | `VwapReclaimRejectionStrategy` (`strategies/movement/vwap_reclaim.py`) | `generate_vwap_reclaim_rejection_candidates` (`strategies/movement/vwap_reclaim.py`) | Yes |
| candidate | `CandidateGenerator` implementations | `CandidateGenerator` implementations | Yes |
| ranking | `build_ranked_opportunity_report` (`core/ranking_orchestrator.py`) | `build_ranked_opportunity_report` (`core/ranking_orchestrator.py`) | Yes |
| persistence | `write_ranked_pipeline_evidence` / custom JSONL append | custom JSONL append (`scripts/run_nifty_vertical_slice_replay.py`) | No, specialized `_persist_trace` used |
