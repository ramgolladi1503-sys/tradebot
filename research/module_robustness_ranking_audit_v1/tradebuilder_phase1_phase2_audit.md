# TradeBuilder, Phase 1, Phase 2 Audit

`strategies/trade_builder.py:TradeBuilder` is reachable and safety-critical. V2 did not certify all valid/reject/stale/fallback/exception paths because a full frozen market context fixture is still required. `core/_engine_phase2_adapter_base.py:build_candidates_phase2` is the clearest Phase 2 owner found; it mutates candidate dictionaries with phase2 scores, hard filters, fallback flags, and soft penalties. Phase 1 aliases remain less cleanly isolated and require a follow-up fixture-backed trace.

Verdict: `NOT_PROVEN` for TradeBuilder/Phase 1 end-to-end correctness; `PARTIALLY_VERIFIED_WITH_GAPS` for Phase 2 static/reason surfaces.
