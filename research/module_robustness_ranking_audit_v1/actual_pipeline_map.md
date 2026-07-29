# Actual Pipeline Map

VERIFIED core read-only ranking path on this HEAD:

`core.ranking_orchestrator.build_ranked_opportunity_report`

1. `core.candidate_pool_orchestrator.build_candidate_pool_report`
2. `core.candidate_normalizer.normalize_candidates`
3. `core.candidate_classifier.classify_candidates`
4. `core.hard_downgrade_engine.apply_hard_downgrades`
5. `core.opportunity_scoring.score_opportunities`
6. `core.directional_balance.analyze_directional_balance`
7. `core.feed_hold_gate.apply_feed_hold_to_ranking` when feed truth is supplied
8. `core.candidate_ranking.rank_candidates`

PARTIALLY_VERIFIED UI projection path:

`dashboard.streamlit_app_runtime` reads top executable/advisory snapshots, but can fall back to visible/advisory or executable filtered rows when canonical top snapshots are empty.

NOT_VERIFIED in this audit: broker/manual approval end-to-end identity preservation from ranked snapshot to order handoff. No broker APIs were called.
