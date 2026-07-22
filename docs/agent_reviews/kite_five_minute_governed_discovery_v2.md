mode: research_audit_repair
candidate_id: kite-five-minute-governed-discovery-v2
decision: evidence_repaired_without_merge
reason: v1 placeholder verdict was invalidated; v2 implemented distinct mechanisms and real underlying forward returns
timestamp: 2026-07-22T00:00:00Z
is_order_action: false
broker_api_called: false
source: local_kite_archive_release_asset

# Agent Work Contract

source_agent: Codex
action: GENERATE_PATCH
title: Repair Kite five-minute governed discovery PR evidence
scope: research/kite_five_minute_campaign, research/data_governance, tests, scripts, workflow, and agent review evidence
requested_paths: research/kite_five_minute_campaign, scripts, tests, .github/workflows, docs/agent_reviews
allowed_paths: research/kite_five_minute_campaign, research/data_governance, scripts/run_kite_five_minute_campaign.py, scripts/audit_kite_five_minute_campaign.py, tests/test_kite_five_minute_campaign*.py, .github/workflows/kite_five_minute_governed_discovery.yml, docs/agent_reviews/kite_five_minute_governed_discovery_v2.md
forbidden_paths: broker APIs, order routing, live execution, feed truth, fallback behavior, risk gates, dashboards, production strategies, option replay, real-money configuration, PR #694 evidence, prospective sealed outcomes
expected_tests: pytest -q tests/test_kite_five_minute_campaign.py tests/test_kite_five_minute_campaign_v2.py
acceptance_proof: v1 invalidation record, v2 freeze manifest, synthetic positive/null/negative tests, real v2 evidence, sidecar verification, prohibited-file diff

# Scope Guard

No production broker, order, live-risk, feed, dashboard, strategy-threshold, option-replay, real-money, PR #694, or prospective outcome paths were modified. The raw Kite archive was not committed.

# Grill Me Review

The prior v1 campaign result was structurally invalid because it used one cross-index signal as all mechanism labels, treated signal magnitude as PnL, used placeholder bootstrap and p-values, hard-coded gates, and let the audit import primary logic. That result is preserved only under `research/kite_five_minute_campaign/evidence/invalid_v1_placeholder/` with status `INVALID_IMPLEMENTATION`.

# Hermes Review

The v2 lane freezes `kite-five-minute-governed-discovery-v2`, four mechanism families, 24 variants, 2.0 bps cost, candle-open timestamp semantics, next-bar entry, frozen holding-period exit, 10,000 bootstrap resamples, and 10,000 max-stat permutations. The pre-outcome freeze manifest binds code commit `b5dc6074c756de41df53914e259b4a489ab3f478`, archive SHA, accepted manifest SHA, v2 contract hash, and all variants.

# GSD Review

Implemented v1 invalidation, v2 contract/engine/statistics, synthetic tests proving the pipeline can pass and reject null/negative fixtures, real-data v2 execution after freeze, workflow push/PR trigger repair, and v2 audit output. The PR remains draft and unmerged.

# QA / Safety Review

Focused tests passed locally: `30 passed in 38.59s`. Sidecar verification checked 39 sidecars with no mismatches. Prohibited-file diff check returned no production/high-risk path changes.

# Acceptance Proof

Synthetic positive control passes all candidate gates. Synthetic null and negative-direction fixtures produce no candidate. Real v2 run produced `NO_EDGE_FOUND_WITHIN_PREREGISTERED_SEARCH_BUDGET` with `candidate_bundle_hash=null`, based on actual NIFTY entry/exit returns, not signal magnitude.

# Runtime Proof Required After Merge

No live runtime proof is required or claimed for this research-only PR. Remote workflow artifact verification remains required before publication-grade acceptance because workflow execution depends on GitHub running the branch push/PR trigger.

# What This PR Does Not Prove

This does not prove profitability, option edge, paper readiness, live readiness, production readiness, or future confirmation success. It only repairs the historical five-minute underlying development campaign mechanics.

# Human Approval

No merge approval is requested. Human review is required before merging PR #696 or treating any v2 result as publishable.
