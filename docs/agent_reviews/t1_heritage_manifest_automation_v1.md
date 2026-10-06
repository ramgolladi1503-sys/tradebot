# T-1 Market Heritage Manifest Automation Contract

## Agent Work Contract

- `source_agent: hermes` for architecture, contract, workflow, and acceptance design; followed by `source_agent: gsd` for scoped implementation, tests, and verification.
- `action: DESIGN_ARCHITECTURE, DEFINE_CONTRACT, MAP_WORKFLOW, CREATE_ACCEPTANCE_GATES, UPDATE_DOCS` for Hermes; `PLAN_PR, GENERATE_TESTS, GENERATE_PATCH, FIX_TEST_FAILURE, UPDATE_DOCS` for GSD.
- `title: Automated T-1 market heritage manifest publishing and live launch integration`.
- `scope: Provide an automated post-market publisher script to construct, cryptographically verify, and index immutable T-1 market heritage manifests. Extend the immutable live launch plan contract and live orchestrator CLI to accept and bind verified heritage manifests, unblocking non-CAS strategies without weakening fail-closed invariants or synthesizing unverified data.`
- `requested_paths: core/market_event_graph_live_launch_plan.py; scripts/publish_t1_heritage_manifest.py; scripts/run_market_event_graph_live_session_v1.py; tests/test_publish_t1_heritage_manifest.py; docs/agent_reviews/t1_heritage_manifest_automation_v1.md`.
- `allowed_paths: exactly the requested paths`.
- `forbidden_paths: broker/order/execution/risk/strategy code; credentials or environment files; runtime session data modification; safety-gate weakening; synthetic or forward-filled market data; unrelated test shims or files`.
- `expected_tests: automated publishing of verified manifests, independent verification via verify_market_heritage_manifest, loading verified prerequisites into StrategyShadowAdapterRegistry with READY verdicts, launch plan basis hash stability, and fail-closed behavior on missing or unverified manifests`.
- `acceptance_proof: generated manifests pass independent cryptographic verification; verified prerequisites arm non-CAS strategies with READY verdicts and evaluation eligibility; AGENTS.md trading invariants (read_only=true, is_order_action=false, broker_api_called=false, allowed_for_live_execution=false) hold; focused unit tests pass; full health gate passes; git diff --check passes`.

## Scope Guard

This implementation automates the post-market publishing of genuine T-1 market heritage evidence from verified completed session data and integrates its path and cryptographic hash into the live launch plan. It does not alter live order routing, broker adapters, execution engines, risk thresholds, kill switches, feed freshness gates, or strategy parameters. All evidence and verification remain read-only.

## Grill Me Review

- The manifest must bind genuine predecessor session evidence and calendar relationships; synthesizing or forward-filling missing bars or close prices is strictly forbidden.
- Loading must remain fail-closed: if the manifest path, hash, or semantic verification is absent or fails, non-CAS strategies must remain blocked (`PINNED_HERITAGE_MANIFEST_REQUIRED` or `BLOCKED`).
- Decision epochs must prevent future information leakage (`available_epoch <= decision_epoch`).
- The live launch plan must hash-bind the manifest path and SHA-256 into its immutable identity.

## Hermes Review

The architecture extends the existing `core.market_heritage_graph` and `core.market_heritage_verifier` modules without modifying their verified rules:
1. `scripts/publish_t1_heritage_manifest.py` constructs a `HeritageGraph` containing calendar predecessor nodes, futures contract identity, 15:29:00 futures bar, daily close, and rolling 200-session daily series, verifies them, writes the content-addressed manifest to the approved root, and registers it into `SessionHeritageIndex`.
2. `core/market_event_graph_live_launch_plan.py` incorporates optional heritage parameters into the immutable launch plan dictionary and its canonical SHA-256 basis.
3. `scripts/run_market_event_graph_live_session_v1.py` exposes `--heritage-manifest` to ingest the verified manifest file and pass its path and SHA-256 into the production launch plan.
4. `core/kite_read_only_observation_runtime.py` already natively reads `heritage_manifest_path` and `heritage_manifest_sha256` from the launch plan to arm `StrategyShadowAdapterRegistry`.

## GSD Review

GSD implemented:
- `scripts/publish_t1_heritage_manifest.py`: automated CLI publisher with strict input verification and independent manifest re-verification.
- `core/market_event_graph_live_launch_plan.py`: added `heritage_manifest_path`, `heritage_manifest_sha256`, `venue`, `calendar_id`, `calendar_version`, `selected_futures_contract_key`, `target_expiry` to launch plan construction and loading while preserving backward compatibility.
- `scripts/run_market_event_graph_live_session_v1.py`: added `--heritage-manifest` CLI flag.
- `tests/test_publish_t1_heritage_manifest.py`: unit tests verifying end-to-end publishing, independent verification, and prerequisite loading.

## QA / Safety Review

**High-Risk Path Review:** Although neither `config/` nor `core/execution/` was touched, changes to `scripts/run_market_event_graph_live_session_v1.py` affect the live launch orchestrator. This change adds read-only manifest parameters and retains all preflight and launch validation gates. Zero broker APIs are called, zero order actions are performed, and live execution remains disabled.

## Acceptance Proof

- Automated test suite `tests/test_publish_t1_heritage_manifest.py` passes 2/2.
- Related suites pass:
  - `tests/test_market_event_graph_live_launch_plan.py`: 12/12 passed.
  - `tests/test_market_heritage_graph.py`: 69/69 passed.
  - `tests/paper_shadow/test_t1_scenario_f_missing_manifest.py`: 2/2 passed.
- Official 2026-10-07 manifest published to `/Volumes/TradeBotData/sessions/heritage-c10b48b8a9a3a459d15ae2aca859723e96e27c51fa2da18b52e3b7672fbe5221.json` with SHA-256 `a0deb13b4715110ac25108020c111069b810b03531757ec2fe8406d85900be5b` and verdict `PASS_VERIFIED`.
- `load_verified_t1_prerequisites` arms all 3 non-CAS strategies (`INTRADAY_OPENING_DRIVE_V1`, `S1_MOMENTUM_OVERNIGHT_V1`, `S4_MONDAY_OVERNIGHT_V1`) as `READY` with zero disabled strategies.
- `python scripts/validate_agent_review_evidence.py --base-ref origin/main --candidate-ref HEAD` passes.
- `git diff --check origin/main..HEAD` passes cleanly.

## Runtime Proof Required After Merge

In tomorrow's morning preflight (`2026-10-07`), run:
```bash
python scripts/run_market_event_graph_live_session_v1.py \
  --session-date 2026-10-07 \
  --heritage-manifest /Volumes/TradeBotData/sessions/heritage-c10b48b8a9a3a459d15ae2aca859723e96e27c51fa2da18b52e3b7672fbe5221.json
```
Verify that `presession_manifest.json` logs status `VERIFIED` and non-CAS shadow adapters transition to `READY`.

## What This PR Does Not Prove

It does not prove future broker data availability, future tick collector uptime, or live strategy profitability. It does not synthesize data when historical bars are missing.

## Human Approval

Human review and approval is required for merge and live deployment.
