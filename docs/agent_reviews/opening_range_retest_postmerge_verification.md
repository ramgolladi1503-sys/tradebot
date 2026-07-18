# Opening Range Retest Post-Merge Verification

## Agent Work Contract

- source_agent: Codex
- action: UPDATE_DOCS
- title: Verify ORB replay after merged partition fix
- scope: Publish bounded post-merge verification evidence for Opening Range Retest Phase 1 after PR #671 merged.
- requested_paths: `docs/agent_reviews/opening_range_retest_postmerge_verification_v1.json`, `docs/agent_reviews/opening_range_retest_postmerge_verification_v1.json.sha256`, `docs/agent_reviews/opening_range_retest_postmerge_verification.md`, `docs/agent_reviews/opening_range_retest_causal_replay_phase1.md`
- allowed_paths: same as requested paths
- forbidden_paths: production strategy files, `core/`, `config/`, broker paths, execution paths, risk paths, feed paths, dashboard paths, credentials, authoritative corpus roots, runtime strategy wiring
- expected_tests: five-session authoritative smoke and audit, 12-shard authoritative replay, strict shard merge, independent merged audit, explicit partition assignment invariant check, py_compile, ruff, diff check, agent-review evidence validation, scoped CE gate
- acceptance_proof: `ORB_POSTMERGE_VERIFIED`

## Scope Guard

This is documentation-only post-merge evidence publication. It records replay artifacts generated from exact merged `origin/main` and does not change production code, strategy logic, runtime wiring, broker behavior, risk gates, feed gates, profiles, credentials, or corpus roots.

## Repository Evidence Fields

- mode: RESEARCH_REPLAY_ARTIFACT
- candidate_id: opening_range_retest_postmerge_verification_v1
- decision: ORB_POSTMERGE_VERIFIED
- reason: Exact merged `origin/main` completed authoritative smoke, 12-shard replay, strict merge, independent audit, and explicit partition invariant checks.
- timestamp: 2026-07-19T01:35:00+05:30
- read_only: true
- append: false
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- source: docs/agent_reviews/opening_range_retest_postmerge_verification.md

## Grill Me Review

The earlier post-merge run at `/tmp/orb-postmerge-8646a238-12shard-1784396700` correctly failed independent audit with `partition_assignment_count_mismatch`: 12 child shards and the merged summary were READY, but the merged source manifest had 1512 records and zero `partition_assignments`. PR #671 fixed that merge-path evidence defect. This verification reran from exact merged `origin/main=140025d8fc288c2a1c24351e1b242a54bd6a0576` and now proves the retained failure path is repaired.

## Hermes Review

The final accepted topology is an authoritative 12-shard replay with deterministic shard assignment by `sha256(canonical_session_key) mod 12`. The merged source manifest retained 1512 source records and 1512 partition assignments; an explicit invariant scan found `partition_errors=0`.

## GSD Review

Generated evidence:

- Smoke artifacts: `/tmp/orb-postmerge-final-140025d8-smoke-1784401556`
- Full replay artifacts: `/tmp/orb-postmerge-final-140025d8-12shard-1784401606`
- Merged artifact directory: `/tmp/orb-postmerge-final-140025d8-12shard-1784401606/merged`
- Published bounded JSON: `docs/agent_reviews/opening_range_retest_postmerge_verification_v1.json`

## QA / Safety Review

Safety-sensitive claims:

- read_only=true
- append=false
- is_order_action=false
- broker_api_called=false
- allowed_for_live_execution=false

## Acceptance Proof

Five-session authoritative smoke:

- verdict: `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`
- independent audit: `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`
- selected file count: `5`
- candidate count: `6`
- candidate semantic hash: `53f826a8b15dec361df67f2da617b285c124e2df91cd022ca0dcd1282379ea7e`
- canonical summary semantic hash: `598d5c7c292d7904af010d08033d44b0de2a90fdc9a34bbc95773e092c9bb136`

Authoritative 12-shard replay:

- merged verdict: `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`
- independent merged audit: `OPENING_RANGE_RETEST_CAUSAL_REPLAY_READY`
- selected source count: `1512`
- source-universe hash: `cf4cc9cacb2db3a2f9cdc006465ebd5f8af6e6146e6a6a59048e1af38f2393bc`
- candidate count: `2215`
- candidate semantic hash: `53c8cf67f33d1e958bc2ffa1730c00c86d222e67ae76d2e865da6962892e1d24`
- partition assignments: `1512`
- partition assignment errors: `0`
- malformed sessions: `0`
- oracle mismatches: `0`
- future-mutation failures: `0`
- source mutations: `0`
- new commit-bound canonical summary semantic hash: `34b7c8628e28c436a2b18a1d9598077d2e08e0eab09009748e06c2ed41eb9074`

## Runtime Proof Required After Merge

No additional ORB Phase 1 replay proof is required for the current merged `origin/main` SHA. If `origin/main` advances with ORB replay code, source-manifest logic, audit logic, strategy behavior, profile identity, or corpus selection changes, post-merge replay verification must be rerun for that new exact commit.

## What This PR Does Not Prove

This verifies causal signal-generation replay and artifact integrity only. It does not prove structural trading edge, profitability, exact option P&L, execution fills, spread realization, latency behavior, slippage, paper readiness, live readiness, broker correctness, capital allocation readiness, or production promotion.

## Human Approval

This documentation-only PR records post-merge evidence. Human review and merge are required. Codex must not merge this PR or enable auto-merge.
