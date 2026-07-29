# Canonical Ranking Row Contract

Minimum justified fields: `candidate_id`, `ranking_snapshot_id`, `producer`, `strategy_id`, `strategy_version`, `underlying`, `instrument`, `expiry`, `strike`, `option_type`, `signal_direction`, `action_semantics`, `observed_ts`, `signal_ts`, `evaluation_ts`, `source_provenance`, `freshness_state`, `regime_snapshot_id`, `strategy_reason_codes`, `data_quality_state`, `eligibility_state`, `eligibility_reasons`, `risk_annotations`, `score_components`, `final_ranking_score`, `rank`, `display_state`, `executable_state`, `dedupe_group`, and `lifecycle_status`.

Each field addresses an observed ambiguity: fallback UI traceability, score semantics, fallback/degraded provenance, deterministic rank identity, CE/PE directional semantics, and approval handoff identity.
