# PR #817 — Batched Checkpoint Certification Review Evidence

mode: RESEARCH_GOVERNANCE_ONLY
decision: IMPLEMENTATION_CANDIDATE_PENDING_EXACT_HEAD_CI_AND_INDEPENDENT_REVIEW
is_order_action: false
broker_api_called: false

## Agent Work Contract

Objective: reduce repeated repository-wide CI cost while preserving task-local focused/adversarial/integration/regression validation, strict dependency completion for sealing, exact-SHA evidence binding, independent verification, and final program certification. Scope is limited to autonomous-loop governance code, tests, handbook text, and the checkpoint execution policy.

## Scope Guard

In scope: dependency scheduling semantics for provisional build progress, seal-time dependency enforcement, checkpoint certification policy, focused/adversarial tests, and governance documentation.

Out of scope: feed/WebSocket implementation, PR813/PR814 certification work, TradeBuilder, strategies, ranking, risk, broker/order paths, execution behavior, paper/live authority, frozen-model economics, and PR815 evidence-pipeline behavior.

Safety remains `broker_write_authority=false`, `order_authority=false`, `paper_authorized=false`, `live_authorized=false`.

## Grill Me Review

The dangerous shortcut would be to interpret batched CI as permission to treat an unsealed prerequisite as complete. This candidate does not do that. It adds a separate provisional build scheduler that releases a downstream implementation only after the prerequisite reaches `REGRESSION_VALID` or stronger local validation. The strict scheduler is unchanged for final dependency completion.

A second dangerous shortcut would be allowing a downstream task to seal while its prerequisite has merely reached `REGRESSION_VALID`. The supervisor now explicitly rejects `SEALED` when strict dependency completion is not satisfied.

A third failure mode is stale checkpoint evidence. The policy states that checkpoint CI evidence is reusable only for the exact candidate SHA containing the complete claimed changed surface; subsequent code changes require re-certification for final sealing.

## Hermes Review

No broker, order, feed, process-launch, credential, paper/live-authority or trading-runtime boundary is acquired. The modified supervisor remains pure governance state logic. The new policy explicitly protects the ongoing feed certification surface from unrelated CI repair.

## GSD Review

Changed surface is intentionally small: dependency graph, supervisor, framework tests, handbook, and one machine-readable certification execution policy. The implementation does not modify the T01-T35 economic objectives or their exit gates. It changes only when broad repository CI is paid, not whether final CI/independent verification is required.

## QA / Safety Review

Adversarial coverage added for: no provisional release at `INTEGRATION_VALID`; provisional release at `REGRESSION_VALID`; strict scheduler still blocking at `REGRESSION_VALID`; dynamic blockers blocking the provisional scheduler; downstream sealing rejected over an unsealed prerequisite; and sealing allowed only after strict dependency completion plus complete SHA-bound evidence.

No feed/WebSocket test or production feed code is changed.

## Acceptance Proof

Passing requires the exact PR head to pass Autonomous Loop Framework Certification, relevant repository checks, and a later genuinely independent exact-SHA review. A green focused workflow is not by itself program certification. No task is considered sealed merely because checkpoint batching is implemented.

## Runtime Proof Required After Merge

None for this governance-only change. Any later task that requires genuine live observation remains subject to its own live-evidence gates. Unit tests or checkpoint CI cannot substitute for live proof.

## What This PR Does Not Prove

This PR does not prove T01-T35 completion, T36/T37 necessity, structural edge, profitability, live readiness, execution viability, prospective support, or main-merge readiness. It does not authorize fabricating T36/T37 merely to satisfy a numeric release hold.

## Human Approval

No main merge is authorized. This PR targets the autonomous-loop framework research branch only. The framework and program remain held from `main` until the governed program release policy is satisfied and explicit human main-merge authority is provided.
