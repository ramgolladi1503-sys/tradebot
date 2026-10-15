# PR #982 — Morning Readiness and Heritage Manifest Resolver

## Evidence Contract Fields

- mode: LIVE_OBSERVATION_MORNING_READINESS
- candidate_id: pr982-morning-readiness-heritage-manifest-resolver
- decision: REVIEW_ONLY
- reason: Pre-market morning readiness, automated T-1 heritage manifest discovery with holiday/weekend lookback, and ambient credential isolation for governed morning launcher.
- source_agent: gsd
- action: GENERATE_PATCH
- is_order_action: false
- broker_api_called: false
- allowed_for_live_execution: false
- append: false

## Agent Work Contract

- PR: #982
- Branch: `feat/morning-readiness-and-heritage-v1`
- Scope: Implementation and verification of automated T-1 heritage manifest discovery and governed morning launcher readiness:
  - Automated backward calendar lookback across NSE holidays and weekends up to 10 days.
  - Independent cryptographic SHA256 integrity verification via `verify_market_heritage_manifest`.
  - Auto-wiring into `GovernedMorningOrchestrator.step_arm_observer()`.
  - Adding CLI flags `--heritage-manifest` and `--heritage-manifest-sha256` to `scripts/run_governed_morning_observer_v1.py`.
  - Hardening `GovernedAuthCallbackServer` token generation with `BaseException` handling.
- Requested paths:
  - `core/governed_morning_orchestrator.py`
  - `core/heritage_manifest_resolver.py`
  - `scripts/run_governed_morning_observer_v1.py`
  - `tests/test_governed_morning_observer.py`
  - `tests/test_heritage_manifest_resolver.py`
  - `docs/agent_reviews/pr982_morning_readiness_heritage.md`
- Allowed paths: the requested paths above only.
- Forbidden paths/behaviors: broker order placement or modification, secrets, live trading enablement, bypassing risk gates or feed freshness checks, PR818 frozen production surface files.
- Expected tests: 54/54 passing unit and regression tests across morning orchestrator, morning observer, and heritage manifest resolver.
- Acceptance proof: passing local test suite, clean syntax compilation, Cerberus and Minerva gate verification.

## Scope Guard

Verdict: PASS

- All modifications strictly adhere to pre-market launcher orchestration, calendar scanning, cryptographic integrity checks, and error reporting.
- No live broker orders are placed, cancelled, or altered (`is_order_action: false`, `broker_api_called: false`).
- Zero changes to PR818 frozen live-flow surface (`core/market_event_graph_live_runtime_bridge.py` reverted).

## High-Risk Path Review

Verdict: PASS WITH RUNTIME PROOF REQUIRED

`core/governed_morning_orchestrator.py` touches morning launcher execution. Changes are strictly confined to:
1. Auto-resolving valid predecessor session manifests and forwarding verified path/sha256 arguments to child MROS observer command.
2. Graceful `BaseException` handling during auth callback redirect without leaving dangling threads.
All order-execution and risk-gating paths remain un-gated and strictly read-only.

## Grill Me Review

Verdict: PASS

Adversarial critique resolved with empirical constraints:
- Invariant I-1: Holiday and weekend lookback correctly skips non-trading calendar dates up to 10 days backward.
- Invariant I-2: Any tampered manifest or SHA256 discrepancy fails closed without wiring parameters into MROS.
- Invariant I-3: Missing manifest logs notice and allows session to proceed in independent mode without crashing.
- Invariant I-4: Zero order actions, zero credential leaks, strictly read-only telemetry.

## Hermes Review

Verdict: PASS WITH BOUNDED CONTRACT

Architectural invariants I-1 through I-5 formally defined:
- Deterministic `HeritageManifestResolution` structure with `ResolutionStatus`.
- Path traversal bounds and SHA256 cryptographic verification before forwarding.
- Fail-closed isolation between ambient shell environment and auth callback server.

## GSD Review

Verdict: PASS

All scoped work items implemented cleanly with proof-driven tests. Zero shortcuts, zero mock-only tests, and zero bypass of safety gates. 54 tests execute cleanly in under 15 seconds.

## QA / Safety Review

Verdict: PASS

- 54 passed tests locally across all touched test suites.
- Code excellence gates report 0 blocks.
- Non-negotiables verified:
  - `read_only = True`
  - `is_order_action = False`
  - `broker_api_called = False`
  - `allowed_for_live_execution = False`

## Acceptance Proof

```text
pytest tests/test_governed_morning_observer.py tests/test_heritage_manifest_resolver.py tests/test_governed_morning_orchestrator.py -q
54 passed, 3 warnings in 12.21s
```

## Runtime Proof Required After Merge

During tomorrow morning's governed launcher start:
1. Verify automated predecessor manifest resolution in launcher stdout.
2. Confirm child MROS process launches with verified `--heritage-manifest` and `--heritage-manifest-sha256`.

## What This PR Does Not Prove

1. It does not certify algorithmic trading profitability.
2. It does not authorize live automated order placement with capital risk.
3. It does not replace human operator monitoring during market open/close.

## Human Approval

Approved by USER in task prompt: "open a pr for all these fixes and work until ci is green and then merge it to main and get the morning readninsess".
