# Runtime Authority Hardening V1

mode: PAPER
candidate_id: runtime-authority-hardening-v1
decision: REVIEW_ONLY
reason: add fail-closed authority, characterization, shadow-stage and fault-test contracts without changing the working feed or production runtime
timestamp: 2026-07-30T22:30:00+05:30
is_order_action: false
broker_api_called: false
allowed_for_live_execution: false
source: docs/agent_reviews/runtime_authority_hardening_v1.md

## Agent Work Contract

```text
source_agent: ChatGPT GitHub agent
operation: IMPLEMENT_RUNTIME_AUTHORITY_HARDENING_SHADOW_V1
base_commit: 17262b4b6a42eb09d4d508bfdf6fe0d649ee32af
branch: agent/runtime-authority-hardening-v1
scope:
  - freeze feed and configuration paths
  - map runtime authority explicitly
  - add deterministic TradeBuilder characterization
  - add immutable canonical execution decision
  - add extracted shadow orchestration stage semantics
  - separate UI ranking from execution-ranking authority
  - freeze existing orchestrator helper shadowing and reject new shadowing
  - add focused fault and boundary tests
allowed_paths:
  - core/canonical_execution_decision.py
  - core/runtime_authority_contract.py
  - core/trade_builder_characterization.py
  - core/orchestration_stage_pipeline.py
  - core/ranking_authority.py
  - core/orchestrator_shadowing_audit.py
  - core/runtime_hardening_campaign.py
  - scripts/audit_runtime_authority_hardening_v1.py
  - tests/test_canonical_execution_decision.py
  - tests/test_runtime_authority_contract.py
  - tests/test_trade_builder_characterization.py
  - tests/test_orchestration_stage_pipeline.py
  - tests/test_ranking_authority.py
  - tests/test_orchestrator_shadowing_audit.py
  - tests/test_runtime_hardening_campaign.py
  - tests/test_runtime_authority_hardening_audit.py
  - docs/architecture/runtime_authority_hardening_v1.md
  - docs/agent_reviews/runtime_authority_hardening_v1.md
  - .github/workflows/runtime-authority-hardening.yml
forbidden_paths:
  - core/market_data.py
  - core/kite_depth_ws.py
  - core/feed_runtime.py
  - core/feed_health_truth.py
  - core/feed_hold_gate.py
  - core/recovery_state_machine.py
  - core/kite_ws_subprocess.py
  - config/**
  - strategies/**
  - core/risk/**
  - core/execution/**
  - dashboard/**
acceptance:
  - no protected feed/config path changed
  - exactly one mapped broker-routing stage
  - UI-only ranking cannot become execution authority
  - unknown execution-ranking authority fails closed
  - contradictory legacy execution fields block
  - critical stage failures halt downstream action
  - noncritical evidence failures degrade only
  - non-broker stages cannot emit order actions
  - deterministic characterization hashes repeat
  - new orchestrator truth shadowing fails CI
```

## Scope Guard

This PR is additive. It does not modify the existing Orchestrator, TradeBuilder,
feed, strategy, risk, execution, broker, dashboard, or configuration code. The
protected-path audit fails if any working feed or config path enters the diff.

## High-Risk Path Review

Verdict: PASS_WITH_SHADOW_ONLY_BOUNDARY

The new canonical execution decision is fail-closed and read-only. It wraps the
existing executable-truth classifier but is not wired to broker routing. The new
stage kernel permits at most one broker-action stage and rejects order-action
output from every other stage.

## Grill Me Review

Verdict: PASS

- Could this PR disturb the feed? No protected feed or config file is changed, and
  the audit rejects such paths.
- Could a fallback row become executable through the new contract? No; a negative
  executable-truth result blocks even if legacy fields claim execute.
- Could contradictory status fields pass? No; contradictions are reason-coded and
  fail closed.
- Could UI ranking silently control execution? No; UI engines are explicitly
  classified as UI-only and unknown authority cannot be resolved.
- Could an evidence-write exception stop exit safety? The extracted shadow kernel
  treats noncritical evidence failure as degraded while critical failures halt.

## Hermes Review

Verdict: PASS

The architecture separates contracts without rewriting the production runtime:

```text
legacy runtime
-> deterministic characterization
-> canonical shadow decision
-> authority comparison
-> extracted shadow stage semantics
-> no runtime promotion in this PR
```

## GSD Review

Verdict: PASS

The implementation is split into independently testable contracts rather than a
large rewrite. Each stage has one acceptance boundary, and any unknown execution
or ranking authority fails closed. The working feed remains outside the change set.

## QA / Safety Review

Focused coverage includes:

- executable, advisory and blocked canonical decisions;
- fallback and stale truth disagreement with legacy fields;
- missing execution entry;
- positive/negative legacy contradiction;
- protected feed-path rejection;
- one broker authority maximum;
- critical exception halting;
- noncritical evidence failure degradation;
- unauthorized order-action rejection;
- duplicate execution-ranking authority rejection;
- deterministic output hashing;
- AST-only shadowing debt control.

Standalone pre-publication result:

```text
30 passed, 3 repository-dependent checks skipped
```

The repository-dependent checks run in GitHub Actions against the complete checkout.

## Acceptance Proof

Required focused command:

```bash
PYTHONPATH=. DISABLE_ML=true python -m pytest -q \
  tests/test_canonical_execution_decision.py \
  tests/test_runtime_authority_contract.py \
  tests/test_trade_builder_characterization.py \
  tests/test_orchestration_stage_pipeline.py \
  tests/test_ranking_authority.py \
  tests/test_orchestrator_shadowing_audit.py \
  tests/test_runtime_hardening_campaign.py \
  tests/test_runtime_authority_hardening_audit.py
```

Required audit command:

```bash
PYTHONPATH=. DISABLE_ML=true python scripts/audit_runtime_authority_hardening_v1.py \
  --repo-root . \
  --base-ref origin/main
```

Required static checks:

```bash
python -m py_compile \
  core/canonical_execution_decision.py \
  core/runtime_authority_contract.py \
  core/trade_builder_characterization.py \
  core/orchestration_stage_pipeline.py \
  core/ranking_authority.py \
  core/orchestrator_shadowing_audit.py \
  core/runtime_hardening_campaign.py \
  scripts/audit_runtime_authority_hardening_v1.py

git diff --check
python scripts/validate_agent_review_evidence.py
```

Acceptance requires all focused checks, repository gates and the protected feed-path
audit to pass on the final branch head.

## Runtime Proof Required After Merge

No runtime authority is promoted by this PR. Before a later promotion campaign:

- capture the actual candidate-to-risk-to-intent call path from the production loop;
- run TradeBuilder characterization twice on frozen real snapshots and prove exact hashes;
- compare legacy and canonical execution decisions with zero unsafe mismatches;
- identify exactly one execution-ranking authority or retain fail-closed no-authority status;
- run the extracted stage kernel in shadow beside the legacy cycle;
- prove critical and noncritical fault behavior in supervised PAPER mode;
- leave feed, WebSocket, recovery and subscription code unchanged unless a separately
  reproduced defect requires its own isolated campaign.

## What This PR Does Not Prove

This PR does not prove that the shadow contracts already replace the legacy runtime,
that a specific ranking engine controls live intents, or that the Orchestrator and
TradeBuilder can be deleted or rewritten safely. Promotion remains blocked pending
real repository characterization and runtime call-path evidence.

Truthful status:

```text
PASS_SHADOW_HARDENING_PENDING_CI
FEED_PATHS_FROZEN
LEGACY_RUNTIME_UNCHANGED
ALLOWED_FOR_LIVE_EXECUTION_FALSE
```

## Human Approval

Keep the PR draft and unmerged until focused CI, repository-wide checks, the agent
review evidence gate and the authority audit all pass.
