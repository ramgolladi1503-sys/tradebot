# Certified Release Manager V1 task contract

source_agent: Codex
action: GENERATE_PATCH
title: Offline certified release management
scope: Release history, certification selection, impact analysis and offline preparation
requested_paths: core release-management modules, scripts release commands, tests, docs/release_manager, offline Morning Readiness launcher resolution
allowed_paths: core/certified_release_store.py, core/release_change_impact.py, core/release_certification.py, scripts/release_manager.py, scripts/verify_release_manager.py, scripts/release_manager_mutation_campaign.py, scripts/release_manager_prepare_next_session.py, scripts/morning_readiness_cli.py, tests/test_release_*.py, tests/test_morning_readiness_cli.py, docs/release_manager/
forbidden_paths: frozen checkout, credentials.py, .env, secrets, live runtime, broker/order/risk adapters
expected_tests: behavioral storage integrity, concurrency, failed promotion retention, certification gating, independent verifier rejection, launcher release-store resolution, next-session artifact blocking, mutation coverage
acceptance_proof: exact successor SHA, clean scope, primitive test and verifier evidence; no synthetic live claims
broker_connectivity_authorized: false
broker_write_authority: false
order_authority: false
paper_authorized: false
live_execution_authorized: false
expected_broker_methods: []
forbidden_broker_methods: all
credential_boundary: no credential access
runtime_authority_sha: be002d824ff33adf1a3fe176144d61163c3f86c6 (preserved, not launched)
evidence_destination: external task-specific directory under /Volumes/TradeBotData

## Verified topology

Canonical local main: c6161445685334d201f56348f82b294a38e6c7ea; dirty and preserved.
Remote main verified by ls-remote: a68632fcb5cb0f8e3035c1d4f0ab7a4849e66596.
Remote main is the merge base with be002d824ff33adf1a3fe176144d61163c3f86c6.
Morning Readiness is ahead of remote main; it is not already merged.
Candidate base: be002d824ff33adf1a3fe176144d61163c3f86c6.
Candidate branch: ram/mros-certified-release-manager-v1.
Candidate worktree: /Volumes/TradeBotData/worktrees/mros-certified-release-manager-v1.
The shared repository is shallow. No claim of unrelated histories is made.

## Boundaries and staged integration

No existing operational manifest is changed by development. No bootstrap certification is inferred from handoff PASS fields. Historical evidence must be verified before importing a certified release. Offline launcher release-store resolution is implemented under explicit user authorization; live/broker launch remains outside this work. Remote integration and operational promotion are separate reviewable steps after tests and certification.

## Migration and configuration

Storage root is an explicit caller parameter, outside source and existing evidence. New history must be created in a new directory; existing history is never overwritten. No environment configuration or live flags are changed. No deployment has occurred.

## Scope extension: impact foundation

Additional allowed files: core/release_change_impact.py, tests/test_release_change_impact.py, and the impact/dependency matrices in this directory. The graph producer and independent completeness verification are not yet implemented; graph construction in tests is synthetic unit evidence only.

## Validation checkpoint

41 offline tests passed, zero failures. Command: python3 -m py_compile core/certified_release_store.py core/release_change_impact.py core/release_certification.py scripts/verify_release_manager.py scripts/release_manager_mutation_campaign.py scripts/release_manager.py scripts/release_manager_prepare_next_session.py scripts/morning_readiness_cli.py && PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest -q --noconftest -p no:cacheprovider -o addopts= -c /dev/null tests/test_morning_readiness_cli.py tests/test_release_certification.py tests/test_release_manager_verifier.py tests/test_release_manager_mutation_campaign.py tests/test_release_manager_next_session.py tests/test_certified_release_store.py tests/test_release_change_impact.py.

Release Manager mutation artifact: /Volumes/TradeBotData/release-manager-v1/latest/release_manager_mutation_campaign.json, with release_manager_mutations_detected=7/7, broker_api_called=false, orders_placed=0.

Fail-closed next-session sample artifact: /Volumes/TradeBotData/release-manager-v1/latest/next_session_blocked_sample.json, with next_session_status=BLOCKED because the sample store was uninitialized and no authority artifact was supplied.

No operational release store was initialized from the frozen evidence, no operational manifest was promoted, and no broker connectivity was used.

## Integration checkpoint

Controlled integration worktree: /Volumes/TradeBotData/worktrees/mros-release-manager-main-integration-20260909.

Integration branch: ram/mros-release-manager-main-integration-20260909.

Integration candidate SHA: bf9afb6bd7d55f0ed84a5e2201956492f41a240a.

Integration sequence:

1. origin/main a68632fcb5cb0f8e3035c1d4f0ab7a4849e66596 merged with frozen Morning Readiness be002d824ff33adf1a3fe176144d61163c3f86c6.
2. Release Manager candidate 80d826c829fc96b957620ddeac99a15fa89b069d merged on top.
3. Resulting integration candidate bf9afb6bd7d55f0ed84a5e2201956492f41a240a was certified in a sample external release store.

Integration evidence:

- Targeted offline suite: 46 passed in 55.57s.
- Materialized whole-tree compile: /Volumes/TradeBotData/release-manager-v1/latest/whole_tree_compile_integration_bf9afb6b.json, with whole_tree_compile_pass=true, compile_pass_count=3167, compile_failure_count=0.
- Release Manager mutation campaign: /Volumes/TradeBotData/release-manager-v1/latest/release_manager_mutation_campaign_bf9afb6b.json, with release_manager_mutations_detected=7/7.
- Evidence-bound gate manifest: /Volumes/TradeBotData/release-manager-v1/latest/candidate_gate_results_bf9afb6b.json.
- Candidate certification: /Volumes/TradeBotData/release-manager-v1/latest/candidate_certification_bf9afb6b.json, with verdict=PASS and fallback_sha=be002d824ff33adf1a3fe176144d61163c3f86c6.
- Sample promotion: /Volumes/TradeBotData/release-manager-v1/latest/integration_sample_promotion_bf9afb6b.json.
- Independent release verification: /Volumes/TradeBotData/release-manager-v1/latest/independent_release_verification_bf9afb6b.json, with independent_release_verifier_pass=true.
- Next-session readiness sample: /Volumes/TradeBotData/release-manager-v1/latest/next_session_ready_sample_bf9afb6b.json, with next_session_status=READY.

This checkpoint certifies the release-manager integration candidate in an external sample store only. It does not mutate the operational live release pointer, does not push to remote main, and does not authorize live execution.
