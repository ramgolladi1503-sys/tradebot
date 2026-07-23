# Seven-Engine Pipeline Truthfulness Repair Review

mode: AGENT_PIPELINE_REPAIR
candidate_id: SEVEN_ENGINE_PIPELINE_TRUTHFULNESS_V1
decision: DRAFT_REVIEW_REQUIRED
reason: Removes false-success, guessed-input, unverified-cache, and fabricated-certification behavior from the legacy strategy pipeline.
timestamp: 2026-07-22T20:08:00Z
is_order_action: false
broker_api_called: false
source: PR_705_BRANCH_AND_GITHUB_ACTIONS_FAILURE_REVIEW
allowed_for_live_execution: false

## Agent Work Contract

Repair the legacy strategy-research pipeline so incomplete, missing, stale, malformed, or unverifiable stages block or fail rather than report success. Preserve the merged PR #697 governance boundary. The work must remain research and paper-only and must not call a broker, place an order, enable LIVE, alter risk or feed behavior, tune strategy thresholds, or merge itself.

## Scope Guard

In scope: pipeline context provenance, engine-result contracts, pre/post validation, exact artifact inputs, SHA-256 output verification, cache sidecar validation, strict enum parsing, certification fail-closed behavior, Drift separation, and focused regression tests.

Out of scope: broker adapters, order execution, credentials, live configuration, feed logic, risk logic, strategy rules or thresholds, dashboards, profitability claims, and live eligibility.

## Grill Me Review

1. Can process exit code zero certify an engine? No. A success result also requires run identity, strategy identity, verdict, and verified output hashes.
2. Can the pipeline select the newest evidence file? No. Outcomes and Statistics require exact paths supplied by the run context.
3. Can any matching cache file be reused? No. Cache reuse requires a strategy- and engine-matching sidecar plus a matching SHA-256.
4. Can unknown enum text silently become a valid status? No. Unknown values fail closed.
5. Can Certification fabricate VALID, STABLE, or HIGH_CONFIDENCE objects? No. Certification is explicitly blocked until strict real-value deserialization is complete.
6. Is Drift required for initial paper eligibility? No. Drift is a later explicit lifecycle monitor and is not run in the initial certification sequence.

## Hermes Review

The repair uses the control plane merged in PR #697 as the outer governance boundary. It does not claim that all analytical engines are fully certified. This tranche first prevents false positive pipeline results, preserves stage ordering, records blockers, and makes incomplete downstream contracts visible.

## GSD Review

The branch changes only strategy-pipeline research code, certification/statistics parsing, tests, and this review record. No production execution or broker path is modified. The initial six-stage flow is Research, Registry, Truth, Outcomes, Statistics, and Certification. Drift is opt-in only after a certified baseline and paper snapshot are explicitly provided.

## QA / Safety Review

Focused truthfulness tests cover paper-only enforcement, required provenance, required output hashes, exact input selection, cache-manifest absence, strategy mismatch, hash tampering, and initial Drift exclusion. The first CI attempt exposed the pre-existing synthetic pipeline suite as both behaviorally obsolete and invalid proof: it asserted automatic Drift, bare SUCCESS results, hard-coded synthetic strategy blockers, and unverified cache reuse. That obsolete file was removed after the Code Excellence Minerva gate explicitly classified it as `fake_confidence_test_not_valid_proof`. The focused truthfulness suite remained accepted by Minerva. Production safety checks were not relaxed.

## High-Risk Path Review

No broker, order, execution, credential, live configuration, feed, risk, or strategy-threshold path is changed. The high-risk concern in this PR is false certification inside research tooling. The repair addresses that concern by requiring explicit inputs, provenance, verdicts, output hashes, strict parsing, and fail-closed blockers. `allowed_for_live_execution` remains false.

## Acceptance Proof

Acceptance requires all repository checks to pass on one immutable PR head, including both unit-test workflows, Agent Review Evidence, Code Excellence, Repo Forensics, CodeQL, Portfolio CI, and strategy-registry verification. The PR remains draft and unmerged until those checks are green and the remaining limitations are reviewed.

## Runtime Proof Required After Merge

Run one disposable paper-only strategy through the repaired orchestrator using exact input paths for candidate records, traces, evidence, and outputs. Confirm that absent sidecars, altered hashes, unknown enum values, zero executable evidence, incomplete statistical sections, and absent Drift baselines block. Re-run the same immutable inputs twice and compare artifact hashes. Do not invoke a broker or enable LIVE.

## Known Limitation

The strict statistical report deserializer is not implemented in this tranche. Certification therefore blocks with `STRICT_STATISTICS_DESERIALIZER_REQUIRED` rather than constructing optimistic placeholder models. Stage-specific canonical output manifests and a disposable end-to-end research run remain follow-up work.

## What This PR Does Not Prove

This PR does not prove a profitable strategy, structural edge, future returns, correct market data, achievable option fills, full statistical certification, or live readiness. It proves only that the repaired orchestration path does not treat missing or unverified evidence as success.

## Human Approval

Human review is required before merge. No output from this branch is eligible for live execution. Any later production integration requires a separate narrowly scoped PR, fresh evidence, passing governance gates, and explicit approval.
