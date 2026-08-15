# PR824 PR818 Live-Flow Freeze Review

## Agent Work Contract
Objective: add governance that prevents ordinary future pull requests from silently changing the production/configuration surface carrying the exact PR818 live-reviewed lineage now integrated in `main`.

Authority anchors:
- frozen live-reviewed SHA: `d7dc45e7c5c76247e7d1b8abd40ec7682fac2f9b`
- frozen integrated main baseline: `0d2a32290ccbacc76b608ecdae92df9312106198`

Allowed scope is governance/CI evidence only. No production live-flow implementation, thresholds, feed semantics, broker behavior, strategy behavior, or execution authority may be changed by this PR.

## Scope Guard
The candidate is limited to the repo-forensics governance workflow plus this review evidence. The durable `pull_request_target` path uses read-only permissions, checks out trusted `main`, fetches candidate/base SHAs only as Git objects, compares protected paths, and does not check out or execute pull-request content.

A temporary `pull_request` trigger exists only to bootstrap the currently-required status context for this Stage-A PR. After Stage A reaches `main`, the separately named finalize branch `governance/freeze-pr818-live-flow-finalize-v1` is permitted to modify only the repo-forensics workflow so the temporary trigger and exception can be removed. Production-path drift is never exempted.

## Grill Me Review
Challenge: can an unrelated analytics/research PR alter the live-flow surface without detection?

Implementation-side review result: the target-side guard compares the PR base against the frozen integrated production baseline and then compares PR base to PR head across the frozen production and governance paths. Any ordinary drift fails closed.

Challenge: can a PR replace the guard and then execute its replacement in the privileged target context?

Implementation-side review result: no PR-head checkout or PR-head script execution occurs in the `pull_request_target` path. The workflow used by that event is loaded from protected base `main`.

## Hermes Review
The design separates historical evidence from future governance. It does not reinterpret CI as live evidence. `d7dc45e7...` remains the live-reviewed authority; `0d2a322...` is the repository integration baseline. The governance work only constrains future repository drift.

## GSD Review
The mechanism is intentionally narrow and fail-closed. It checks actual Git diffs rather than relying on labels, PR descriptions, or agent assertions. The bootstrap exception is branch-name constrained and governance-file-only, and is scheduled for deletion in the finalize PR.

## QA / Safety Review
Safety boundary remains:
- `broker_write_authority=false`
- `order_authority=false`
- `paper_authorized=false`
- `live_authorized=false`

No live session, broker write, order placement, modification, cancellation, or execution-authority change is part of this work.

Security review identified and repaired a prior unsafe design that checked out PR-head content inside `pull_request_target`. The repaired design keeps target execution on trusted base content and treats PR content only as Git objects for diff inspection.

## Acceptance Proof
Acceptance requires all effective GitHub required checks and broad CI on the exact candidate SHA to be green, including the repo-forensics context and security review. Merge is prohibited while any mandatory check is failing or expected.

The prior candidate `ae404d44c2739315a442e77cabff9475a30df25d` was not accepted: GitHub blocked merge, CodeQL identified unsafe target checkout/cache exposure, agent-review evidence was missing, and one replay-order test failed in one full-suite run. Those findings are not converted to PASS by this document; the repaired candidate must rerun CI.

## Runtime Proof Required After Merge
No fresh live runtime proof is required merely to install this repository-governance guard because it does not change production live-flow code. If a future change to the frozen production surface is genuinely required, that change must use a separately governed recertification process with evidence appropriate to the change, including fresh live evidence where required.

## What This PR Does Not Prove
This PR does not prove profitability, structural edge, execution viability, fresh prospective support, or fresh live verification of the governance merge SHA. It does not make the final `main` merge commit equivalent to the prior live-reviewed SHA.

## Human Approval
The repository owner explicitly requested that the PR818/PR813 live-observed flow be frozen against disturbance from analytics, PR814, PR815, and future PRs, and explicitly instructed that CI be checked until green and the freeze PR merged only after it is green.
