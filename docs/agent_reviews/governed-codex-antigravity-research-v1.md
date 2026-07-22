# Governed Codex + Antigravity Research Control Plane Review

mode: AGENT_RESEARCH_CONTROL_PLANE
candidate_id: GOVERNED_CODEX_ANTIGRAVITY_RESEARCH_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Adds fail-closed role-separated research governance above the existing worktree supervisor.
timestamp: 2026-07-22T16:49:13Z
is_order_action: false
broker_api_called: false
source: PR_697_BRANCH_AND_REPRODUCED_LOCAL_VALIDATION
allowed_for_live_execution: false

## Agent Work Contract

Build one repository-side, fail-closed strategy-research lifecycle using Codex as implementer and Antigravity as independent reviewer. The lifecycle may create research packets, verify committed engineering evidence, validate robustness artifacts, and grant human-approved paper eligibility. It must not invoke a broker, place an order, enable LIVE, weaken safety gates, change strategy thresholds, or merge itself.

## Scope Guard

In scope: frozen pre-outcome hypothesis contracts, role-separated agent packets, existing worktree-supervisor manifest integration, SHA-256 evidence linkage, mandatory validation gates, paper-only approval, CLI commands, documentation, and focused tests.

Out of scope: broker adapters, execution engines, risk logic, feed logic, credentials, live configuration, strategy implementation, parameter tuning, dashboards, model API integration, and autonomous merge or deployment.

## Grill Me Review

1. Can Codex certify its own implementation? No. The configured reviewer must be independent and the review must link to the implementation hash.
2. Can an agent replace the supervisor manifest and recompute the outer file hash? No. The supervised entry point also validates the manifest's internal canonical hash.
3. Can a missing holdout or oracle be ignored? No. All mandatory gates require a passing, hash-pinned artifact.
4. Can validation automatically enable LIVE? No. The state machine ends at human-approved paper eligibility and always reports live execution as false.
5. Can a strategy be edited after outcomes are observed without invalidation? No. The hypothesis is frozen before outcomes, and a rewrite returns to the freeze boundary.

## Hermes Review

The design layers above the existing agent worktree supervisor rather than duplicating git claims, isolated acceptance execution, changed-path verification, or independent review manifests. The research control plane owns lifecycle state and evidence linkage; the existing supervisor remains authoritative for implementation and review evidence. Chat subscriptions are treated as interactive agent interfaces, not production APIs.

## GSD Review

The implementation is isolated to five new files plus this review document. The CLI supports initialization, hypothesis freezing, packet creation, implementation evidence, review evidence, validation evidence, status, and paper approval. No existing runtime path is rewired.

## QA / Safety Review

Focused tests prove initialization is non-executable, incomplete hypotheses fail, implementation cannot precede freeze, forbidden runtime paths are blocked, self-review is blocked, Antigravity rewrite invalidates progress, missing gates fail closed, artifact tampering is detected, hypothesis tampering is detected, forged supervisor internal hashes are rejected, and the successful path grants paper eligibility while live eligibility remains false.

Local validation against the published layering:

- `python -m pytest -q tests/test_governed_strategy_research.py` -> 14 passed.
- `python -m compileall -q core scripts` -> passed.
- CLI initialization check -> `INTAKE`, integrity valid, paper false, live false.

## Acceptance Proof

Acceptance requires all repository CI checks to pass on one immutable PR head, including tests, CI, CodeQL, Code Excellence, Repo Forensics, Portfolio CI, strategy-registry verification, and this agent-review evidence gate. The PR remains draft and unmerged until those results are known.

## Runtime Proof Required After Merge

After merge, run one real research-only smoke workflow in an isolated worktree: initialize a run, freeze a disposable hypothesis, generate a Codex packet, verify that implementation evidence without a real supervisor manifest is rejected, generate an Antigravity auditor packet only after verified implementation evidence, and confirm that no state can produce `allowed_for_live_execution=true`.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, structural edge, future returns, correct market data, achievable option fills, or successful autonomous Codex/Antigravity invocation. It does not repair or certify the older placeholder seven-engine strategy pipeline. It proves only the repository-side governance and evidence boundaries implemented here.

## Human Approval

Human review is required before merge. Human approval inside this control plane can grant paper eligibility only after all deterministic gates pass. Any later production or live integration requires a separate narrowly scoped PR, fresh evidence, explicit approval, and existing TradeBot execution/risk safeguards.
