# PR970 Evidence Verification Standard Review

## Local admission and frozen-base false-positive follow-up

This scoped follow-up adds fail-closed work-item admission to the existing
`submit_agent_work.py` and supervisor `preflight`/`claim` CLIs. Each request
must identify a committed canonical delivery item and embedded task contract;
the admission helper verifies the tracked HEAD bytes, exact SHA-256, item ID,
complete delivery schema, task-contract ID, and exact source/action/title/scope/
requested/allowed/forbidden path lists. Missing, deleted, dirty, stale,
malformed, and mismatched work items block. Accepted submissions require
successful evidence persistence; `--no-evidence` cannot return accepted.

Caller-supplied `--approve`/`--approved-by` values are not authentication.
Medium/high-risk patch work stays blocked until a real authenticated human
approval mechanism exists. The local checks cover only these two entrypoints.
The inventory now lists 17 active `workflow_dispatch` workflows, all
`UNSATISFIED` for pre-work admission, plus two retired triggers: the PR818
auto-write workflow and frozen-head certification manual dispatch. PR #823 is
recorded as merged on 2026-08-15. Universal platform intake, direct GitHub
dispatch trust, branch protection, and authenticated human approval remain
`UNSATISFIED`.

The supervisor resolves the repository relative to caller-selected
`supervisor.worktree_path`; it does not authenticate that repository as the
intended TradeBot project. A committed work-item hash protects bytes but does
not authenticate the item author, reviewer roles, caller identity, or approval.
There is no authenticated project-identity or human-approval guarantee in this
implementation. These are residual authority limits, not evidence of admission.

The CI correction removes only the stale `PR818_FROZEN_MAIN_BASELINE` fetch and
comparison from old pinned baseline `9f1e74c` to PR base `32e6d77`. That
comparison failed because 16 protected paths had already drifted before this
PR, while the exact PR base-to-head protected-path delta at `ab7769d` was empty.
The change therefore removes detection of pre-existing drift on main. It
preserves the trusted `pull_request_target` job, exact head/base fetch,
`frozen_production` and `governance` arrays, fail-closed base-to-head delta
comparison, and exact bootstrap exception. It does not weaken detection of a
protected change introduced by the PR and does not prove that main matches the
older baseline.

The initial PR818 follow-up deleted its auto-write workflow because its
test-only repair was merged in PR #823; at that point no other
workflow-dispatch workflow was retired. The later frozen-head manual-trigger
retirement is documented below. No branch
settings, credentials, runtime, broker, order, risk, feed, live, or strategy
paths are changed. EVS-001's lifecycle history, evidence, and state remain
unchanged; the task contract is recorded in its existing extensions.

Acceptance proof for this follow-up is limited to focused behavior tests,
governance inventory checks, workflow YAML parsing, shell execution against a
synthetic drifted base and protected PR delta, and `git diff --check`. No hosted
exact-head result, PR merge, branch-protection proof, authenticated identity,
or universal intake coverage is claimed here.

## Enforcement follow-up

The verifier now has an `enforce-new-material` mode: structural `ERROR`/`BLOCKING` findings and material paths without a current covering work item fail the command, while explicit `UNVERIFIED` claim findings remain warnings. For current material records it also requires complete Definition of Ready fields, G0/G1/G2/G3/G4/G5/G7 lifecycle evidence, distinct lifecycle role authors where the existing orchestrator checks them, traversal of required state-history stages, and a pre-merge state of `RELEASE_READY`, `PR_OPEN`, or `CI_GREEN`. G6 is omitted because this check runs within PR CI and cannot require its own completed result in advance. PR CI invokes this mode against exact base/head refs and uploads the resulting report. Report-only remains available for diagnosis; strict mode retains its all-findings-block behavior.

The candidate matrix is checked against a required material-prefix set, and regression tests remove each required prefix in turn. This closes that specific bypass only when the verifier containing the check is trusted. The `pull_request` evidence job executes candidate-controlled code and is now named `Candidate-code evidence diagnostics (untrusted)`. The new `pull_request_target` workflow runs the verifier and delivery code at the exact PR base SHA, fetches the exact head, and materializes a candidate archive as data through `--candidate-root` without executing candidate Python, tests, workflow definitions, or checkout filters. The report records both `verifier_source_sha` and `candidate_root_sha`; protected-base mode fails if the supplied verifier source SHA does not equal its checkout HEAD. Each parsed input is byte-compared to the candidate blob, and candidate paths that traverse symlinks are rejected before reading.

This provides a base-authoritative repository PR-diff check for later PRs only; until the exact status is required, it is not a merge-blocking gate. It does not intercept every request sent through Codex, ChatGPT, Claude, or another platform. The intake audit found only downstream PR-time automation; Codex prompts, GitHub issues, local/CLI/MCP work, manual Actions, and other platform requests lack a common fail-closed intake hook. Universal task coverage is `UNSATISFIED`. Classic branch protection requires `repo-forensics-pr-gate`; the active main ruleset requires `unit_tests` and `health_gate`. Neither requires `Trusted base evidence coverage`. This work does not mutate external repository settings. The check grants no merge, research, or runtime authority.

## Unclassified-path fail-closed follow-up

- Changed paths are classified as material, covered by an explicitly trusted non-material exemption, or unclassified. Unclassified paths now produce `BLOCKING` findings and fail `enforce-new-material`; the candidate cannot add, remove, or alter an exemption. A trusted exemption requires a non-empty rationale and owner and cannot overlap any protected material scope.
- The verifier loads `protected_material_path_prefixes` and trusted exemptions from `VERIFICATION_MATRIX.json` in its own checkout (`ROOT`). In the protected-base workflow, this is the exact PR base tree; `--candidate-root` supplies candidate data only. The candidate matrix must preserve the protected prefix set and the trusted exemptions exactly. The required-prefix baseline now lives in JSON rather than Python literals, preserving the repo-wide path-hardening scanner.
- Added four material scope groups missing from the candidate record: `.github/workflows/ci.yml`, `.github/workflows/tests.yml`, `tests/delivery/`, and `docs/agent_reviews/`. The documentation scope covers both changed review documents. EVS-001 assessed paths, registered claim scope, and matrix material scopes now agree for these paths.
- Explicit `UNVERIFIED` claim findings remain non-blocking. This hardening does not satisfy branch protection or universal task-platform intake; both remain unsatisfied until separately verified.
- Validation: `PYTHONPATH=. pytest -q tests/governance/test_evidence_contract.py tests/delivery tests/test_no_hardcoded_paths_repo_wide.py` — 97 passed. JSON parsing and `git diff --check` passed.
- A local synthetic candidate tree (candidate `bed7918df038294e45eb22d7fe826a4aa2e848c8`, parent `2fd43d59989c7031f4d42353389ba3a1153e2472`) ran the trusted candidate-root verifier against `origin/main`: 25 changed paths were material, zero were unclassified, and zero material paths lacked record coverage. Enforcement still failed on EVS-001's three pre-existing lifecycle findings; `CLAIM_UNVERIFIED` remained non-blocking. No lifecycle state, evidence, signoff, or claim status was added or promoted.

## Trusted-base implementation follow-up

- Added `.github/workflows/frozen-head-exact-sha-certification.yml` with a read-only `pull_request_target` job named `Trusted base evidence coverage`. It checks event base/head SHAs, checks out the exact base, fetches the exact head, verifies both SHAs, materializes the candidate with `git archive`, and invokes only the base checkout's verifier. The candidate tree is data-only; the trusted job does not run candidate scripts, tests, or checkout filters.
- Both trusted evidence coverage and advisory evidence diagnostics now also rerun for the `edited` pull-request event, so changing a PR's base target causes the base/head-bound evidence check to be refreshed. This can also rerun for title or body edits; it does not change the trust boundary or make the status required.
- Renamed the ordinary `pull_request` job to `Candidate-code evidence diagnostics (untrusted)` so it cannot be mistaken for the trusted status.
- Added `--candidate-root` and `--verifier-source-sha`. The verifier checks and records candidate-root HEAD and verifier-checkout HEAD in its report, and refuses separate-root operation without explicit verifier source SHA. Candidate-controlled symlink inputs fail closed.
- Retained active settings as read back: classic protection requires `repo-forensics-pr-gate`; the active main ruleset requires `unit_tests` and `health_gate`, not `Trusted base evidence coverage`. Universal task-intake coverage remains `UNSATISFIED`.
- Bootstrap limitation: this PR cannot cause its newly added base workflow to execute for itself. A later PR whose base already includes the workflow is required to exercise the trusted check. A required-check ruleset update and readback are also still required; neither is performed here.

## RAG CI duplicate-run follow-up

- Restricted `.github/workflows/rag-ci.yml` push-triggered runs to `main`. For a feature branch with an open PR, the same path-filtered RAG job ran on both the `push` and `pull_request` events for the exact same SHA; removing the branch push trigger avoids that duplicate.
- Kept the push and pull-request path filters identical. The `pull_request` event, retrieval contract job, concurrency cancellation, test/evaluation steps, and required evidence artifact behavior are unchanged. The GitHub token remains limited to `contents: read`; local workspace/artifact writes remain part of the job. Main branch pushes remain covered.
- Added a regression that verifies the `main` push restriction, matching event path filters, and core job/permission/failure invariants. Registered the workflow as protected material and included it in the existing evidence claim and EVS-001 assessed paths.
- No CI status check or required-check configuration is suppressed or removed. The separate frozen-head manual-dispatch remediation and its exact-head CodeQL result are recorded below.
- RAG validation now runs for matching pull requests and matching pushes to `main`. A standalone non-main branch with no open PR intentionally has no RAG-specific check until a PR opens, so it loses early RAG-specific feedback. Live branch-settings readback: classic branch protection requires `repo-forensics-pr-gate`; active ruleset `16156361` requires `unit_tests` and `health_gate`; none requires RAG CI. Technical & Quant accepted this tradeoff with no further change requested. This trigger shape follows the existing `ci.yml` and `portfolio-ci.yml` main-push/PR precedent.
- Exact hosted RAG proof: commit `98098cdd8f744f4156ea6446c8f8a1b60dfadf7c` ran RAG workflow run `38016905886` for the `pull_request` event; the full job passed in 1m58s. No feature-branch `push` run occurred for that SHA. One local governance suite passed: `PYTHONPATH=. pytest -q tests/governance/test_evidence_contract.py` — 82 passed. Changed JSON/workflow YAML parsing and `git diff --check` also passed.
- At the prior hosted head, CodeQL reported a high cache-poisoning alert on the frozen-head workflow. The exact-head CodeQL result after trigger retirement is recorded below. The current PR's `pr818-live-flow-freeze-target` still fails in run `38022692504`: the protected-base workflow compares the frozen baseline `9f1e74...` to PR base `32e6d77...` and reports `PR818_FROZEN_MAIN_BASELINE_DRIFT`. This candidate removes that stale baseline-to-PR-base comparison, but this PR's `pull_request_target` run uses the protected base workflow, so the correction cannot affect this run until it is on `main`. Branch settings readback shows this failed status is not required by main's classic protection or active ruleset.

## Post-development verification and dispositions

- Focused validation after verifier lifecycle and required-prefix hardening: `python -m pytest -q tests/governance/test_evidence_contract.py tests/delivery` — 80 passed, with two existing pandas dependency compatibility warnings. `git diff --check` and governance JSON parsing passed.
- QA verified uncovered material paths, explicit `UNVERIFIED` warning behavior, lifecycle evidence/state-history blocking, complete lifecycle record acceptance without upgrading the claim, required-prefix deletion detection, and frozen expected-prefix consistency. This test suite validates the current candidate implementation; it does not make candidate-controlled code trusted.
- Exact-head PR evidence workflow run 37989170331 at `b03c86cd43553e9c71e6701b8417f9e050d888e7` failed closed with three blocking lifecycle findings: EVS-001 remains `BACKLOG` without state history or G0/G1/G2/G3/G4/G5/G7 evidence. The separate `CLAIM_UNVERIFIED` finding remained nonblocking. Report SHA-256: `3a479f9f0be08940811ae4b6f7083f1b21abffa892bfdce512a3f2bbe7d74117`. The initial run exposed a diagnostic usability gap; the next exact-head run printed blocking codes and details to the Actions log.
- BA, Hermes, QA, Senior QA, and UAT: block objective-level acceptance while the candidate work item remains incomplete and the trust, branch-rule, and task-intake gaps remain. Scoped verifier mechanics pass tests; universal coverage remains `UNSATISFIED`.
- Branch settings readback: classic protection requires `repo-forensics-pr-gate`; active ruleset 16156361 requires `unit_tests` and `health_gate`. Neither requires the evidence status.

## Agent Work Contract

- Work item: `EVS-001`, report-only Evidence & Verification Standard.
- Candidate: `49509c2fa20d33ac3e4b2770216590403db1dcd0` (initial reviewed commit; updated on follow-up commits as applicable).
- Scope: existing `core.delivery` validation/readiness, offline verifier, PR-only report, governance docs/data, and tests.
- Prohibited scope: runtime wiring, broker/order APIs, credentials, risk, feed, strategies, and live configuration.
- Safety invariants: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, evidence/contracts are not appended by the verifier.

## Scope Guard

Changed paths are limited to delivery evidence types/validation/readiness, governance policy and registries, the offline verifier and pull-request-only workflow, documentation, tests, and this review record. No high-risk runtime path was changed. No new config keys were added.

## Grill Me Review

Assigned reviewer: `/root/stage0_grill_me` (separate review agent). The review identified existing evidence infrastructure and warned that hash integrity does not authenticate source authority, reviewer identity, or scientific truth. The implementation reuses `core.delivery`, keeps N/A distinct from pass, preserves negative/unverified states, binds reports to candidate inputs, and does not present diagnostics as readiness. No unresolved safety blocker was reported for the scoped report-only change.

## Hermes Review

Assigned reviewer: `/root/stage1_hermes` (separate architecture agent). Hermes recommended a pure offline extension of the existing ledger and four claim-level dimensions, with candidate-bound evidence, explicit limits, and no runtime/broker authority. Post-development responses led to structural-only assessment of declared `VERIFIED` and a required known evidence reference for both claim-level and work-item-level `NOT_APPLICABLE`.

## GSD Review

Assigned implementer: `/root/stage_gsd` (separate implementation agent for regression coverage). GSD added candidate-tree mismatch and declared-status assessment tests. The primary implementation was authored by the task coordinator before this narrow GSD test assignment; this record does not attribute that implementation to GSD.

## QA / Safety Review

- QA: `/root/stage_qa` separately ran the focused governance and delivery suite; final result: 56 passed with two existing pandas dependency warnings.
- Senior QA: `/root/stage2_senior_qa` returned `PASS` after checking path boundaries, current-record coverage, contract-hash binding, structural-only claim assessment, N/A references, candidate-tree equality, and regression coverage.
- Technical & Quant Analyst: `/root/stage_quant` closed the artifact-status and N/A reference findings for this report-only milestone. Artifact bytes, reviewer identity, source authority, and scientific judgment remain unauthenticated; consumers must use assessed status.

## Acceptance Proof

- Focused validation: `python -m pytest -q tests/governance/test_evidence_contract.py tests/delivery` — 56 passed.
- Python compilation, governance JSON parsing, workflow YAML and extracted shell syntax, and `git diff --check` passed.
- Exact candidate report at `49509c2fa20d33ac3e4b2770216590403db1dcd0`, against base `32e6d77130b748b6644e93376fe948b3cd7b9eb9`: 19 material paths, zero `ERROR` findings, and one expected `UNVERIFIED` finding for EVS-001.
- UAT: `/root/stage_uat` returned `PASS` for the report-only deliverable and pending-baseline process.
- Product Owner: `/root/stage_po` accepted the measurement capture process; numeric adoption measurements remain pending the first reviewed PR.
- Release Manager: `/root/stage_rm` found the draft PR eligible, with no merge approval.

## Runtime Proof Required After Merge

No runtime proof is claimed or needed to validate this PR's documented, offline report-only behavior. Any future claim of runtime, research, or trading readiness requires its own authorized, exact-subject verification and cannot be inferred from this PR or its tests.

## What This PR Does Not Prove

- It does not certify any legacy feed, risk, execution, strategy, predictive-validity, or profitability claim.
- It does not authenticate artifact bytes from SHA-shaped references, reviewer identities, or source authority.
- The numeric adoption baseline and false-positive dispositions remain pending the first reviewed PR.
- It does not establish merge, deployment, paper/live readiness, or broker behavior.

## Human Approval

The user authorized implementing the attached proposal and opening a draft PR. This authorization does not approve merge, deployment, credential changes, runtime changes, or live trading actions. No merge was performed or requested.

## Manual workflow entrypoint taxonomy and evidence remediation

- The inventory now separates primary purpose from effects. Its exact purpose enum is `TASK_INTAKE`, `VALIDATION_DIAGNOSTIC`, `CERTIFICATION_RESEARCH`, and `UNKNOWN`; `review_status` independently records `REVIEWED` or `UNREVIEWED`. The Product Owner accepted the corrected mapping: 10 validation/diagnostic, 6 certification/research, 1 active unknown, and no task-intake workflow identified from YAML. The frozen-head manual trigger accounted for the removed second unknown classification. `ai-reliability-pr763-certification.yml` is validation/diagnostic; `feed-resource-soak.yml` and `prospective-market-evidence-v1.yml` are certification/research. Code Excellence remains `UNKNOWN`/`UNREVIEWED`; frozen-head manual dispatch is retired and is no longer part of the active purpose mapping.
- Effect declarations are orthogonal and use `DECLARED`, `NOT_DECLARED_IN_YAML`, or `UNKNOWN` with source evidence for artifact upload paths, local workspace writes, external network/API activity, external mutation, secret references, and permissions. `NOT_DECLARED_IN_YAML` is only a source scan result and is never represented as safety or absence. Invoked script/action behavior, effective permissions, runtime side effects, and GitHub dispatch/ref semantics remain unknown unless separately verified.
- Each classification cites exact YAML line text and the source file's SHA-256. Regression tests regenerate selected-ref and effect evidence from every active workflow and compare it to the inventory; the Code Excellence multiline artifact path is expanded to its four exact output paths from lines 153–157. Any workflow-byte drift, missing or invalid evidence, unlisted dispatch trigger, or admission-state promotion fails the focused suite.
- All 17 active workflows remain `prework_admission=UNSATISFIED`. Arbitrary platform intake, dispatch trust, branch-protection requirement, and authenticated human identity remain `UNSATISFIED`. This change inventories and detects drift; it does not intercept or admit workflow dispatches. The frozen-head workflow trigger changed; no branch setting changed.
- Sixteen of the 17 active purpose mappings are marked `REVIEWED` against the Product Owner accepted mapping. This is role-based review evidence only: no natural-person identity or human signoff is authenticated by the inventory, and the PO class review does not authenticate the PO's identity. The one active `UNKNOWN` entry remains `UNREVIEWED`. EVS-001 remains `BACKLOG` with empty lifecycle history/evidence; only its task-contract extension was revised.
- QA remediation: the evidence scanner now records dash-prefixed inline `- run:` steps as declared code execution, alongside block-form `run:` keys. The `cas-closing-auction-shadow-v1.yml` inline test command is now captured; because the invoked test/script behavior is not established by that YAML line, its external mutation status is `UNKNOWN`. An independent literal fixture asserts this behavior.
- Validation: earlier inventory cycle `PYTHONPATH=. pytest -q tests/governance/test_task_entrypoint_inventory.py` — 9 passed; final seven-file focused suite `PYTHONPATH=. pytest -q tests/test_frozen_head_exact_sha_workflow.py tests/governance/test_task_entrypoint_inventory.py tests/governance/test_evidence_contract.py` — 95 passed; JSON/YAML parsing and `git diff --check` passed.

## Exact-candidate evidence coverage recheck

- Running `enforce-new-material` on the exact candidate `16cf67bc0ce7eb14a0ec2645ecc32dda5472987c` found that `tests/test_frozen_head_exact_sha_workflow.py` was absent from the material matrix, EVS-001 assessed/allowed paths, and the implementation claim scope. This was a genuine fail-closed coverage finding, not a reason to suppress the gate.
- Added that exact test path as candidate material and included it in the current work item, assessment, and claim scope. The protected-base prefix floor is unchanged; unknown paths still block, and the candidate cannot create trusted non-material exemptions. A regression assertion covers the material, allowed, assessed, and claimed path mapping.
- Recorded the narrow correction in EVS-001 task contract `EVS-EXACT-HEAD-MATERIAL-PATH-COVERAGE-2026-10`; its allowed paths exclude runtime and external repository settings.
- Candidate-code local enforcement at `fb36c52f163754353290e026dec914a5a6be0e9a` classified all 41 changed paths as material and reported zero unclassified paths or uncovered material paths. It exited blocked on exactly three existing EVS-001 lifecycle/state findings; `CLAIM_UNVERIFIED` remained a warning. The exact verifier report records candidate, candidate-root, and verifier-source SHA `fb36c52f163754353290e026dec914a5a6be0e9a` and report digest `3697050d2618406db32145ddebcf155c08fc8a672fb6e03274a5abf8380fe2c4`.
- This is local candidate-code validation, not a hosted trusted-base run: the current PR base does not yet contain the verifier workflow, so `pull_request_target` cannot run it on this bootstrap PR. The hosted candidate-code diagnostics remain advisory. Required-check settings and universal task intake remain `UNSATISFIED`.
- EVS-001 remains `BACKLOG` with empty lifecycle history/evidence. Exact-candidate enforcement therefore remains blocked on its incomplete lifecycle evidence and state. No lifecycle evidence or claim verification was fabricated. The trusted workflow still cannot exercise itself until its base workflow is present; branch protection still does not require its status, and those gaps remain `UNSATISFIED`.

## Privileged manual dispatch retirement

- Removed `workflow_dispatch` and its `pr_number`, `candidate_sha`, and `base_sha` caller inputs from `.github/workflows/frozen-head-exact-sha-certification.yml`; removed corresponding input fallbacks from job environments. The workflow now runs only on its existing `pull_request_target` events. Exact-SHA identity, base-authoritative validation, read-only permissions, trusted evidence coverage, and PR status jobs are retained.
- Restricted the entire `pull_request_target` workflow to PRs targeting `main`, with a defense-in-depth `base.ref == 'main'` condition on trusted evidence coverage. This was required because the workflow and verifier use code from the PR base SHA, while only `main` branch protection has been verified. The existing event types and all five jobs remain for main-target PRs.
- This deliberately retires the previously documented non-main-target certification path from PR814 (`frozen_head_validator_non_main_base_v1.md`). All five workflow jobs/statuses stop running for non-main-target PRs. That is a real coverage reduction for those targets; their branch protection and verifier authority are not verified, so this PR does not claim trusted certification coverage there. The historical PR814 document records prior behavior, not proof of protected target authority.
- The Actions UI no longer offers manual dispatch for frozen-head certification. Product Owner review found no documented operator/runbook use for that route. CodeQL reported a high untrusted-ref execution finding on this privileged workflow; retiring the caller-selected route is the scoped remediation. On exact candidate head `badda0a11d00f1555e41c2ca95c4f40871c59ddc`, CodeQL Advanced `Analyze (actions)` and `Analyze (python)` passed (run `38022693862`), and PR check `CodeQL` passed with “No new alerts in code changed by this pull request” (check run `114127074394`). This verifies no CodeQL alert remains in the changed PR content at that head; the workflow remains subject to hosted checks on any later head.
- Inventory now contains 17 active dispatch paths with accepted counts 10 validation/diagnostic, 6 certification/research, and 1 unknown. Frozen-head manual dispatch is recorded as retired with the prior workflow SHA-256 and source location. Existing admissions remain `UNSATISFIED`; no external intake support or required branch-protection gate is claimed.
- Regression coverage verifies the retired trigger and caller input fallbacks are absent; `pull_request_target` stays restricted to `main` with all existing event types, five jobs, and read-only permissions; and exact inventory parity and the 10/6/1 mapping hold. `PYTHONPATH=. pytest -q tests/test_frozen_head_exact_sha_workflow.py tests/governance/test_task_entrypoint_inventory.py` — 13 passed. `PYTHONPATH=. pytest -q tests/governance/test_evidence_contract.py` — 82 passed. JSON/YAML parsing and `git diff --check` passed.
- No job/check definition or required-status configuration was removed for PRs targeting `main`; the workflow intentionally provides no checks for non-main-target PRs until their base authority is verified. No branch settings, runtime, broker/order, risk, feed, credentials, or strategy paths changed.

## One-time bootstrap merge boundary

This PR implements the evidence-verification lifecycle and its trusted-base
workflow, but its own base cannot yet use that workflow as trusted authority.
That bootstrap limitation does not make EVS-001 complete. EVS-001 remains
`REQUIREMENT_READY` with incomplete lifecycle evidence; no missing stage is
implied passed by this implementation.

There is no candidate-code exception, verifier bypass, or reusable merge
waiver. If the repository owner chooses to merge this bootstrap PR, that is a
one-time external repository decision. The decision must be recorded outside
the candidate-controlled checks and pinned to repository
`ramgolladi1503-sys/tradebot`, PR #970, base
`32e6d77130b748b6644e93376fe948b3cd7b9eb9`, and the exact final head SHA. It
must cite the exact required-check run IDs/results, resolve pending checks,
disposition any failed check based on its actual cause, and include an
independent human review. Any base or head change invalidates that disposition
and requires a fresh decision. It applies only to this bootstrap merge and
does not change required checks or authorize future PRs.

At the observed head `914d2b816b0a0ec52cd405be1cb6bbabf6e0c018`, this
disposition is `PENDING / NOT AUTHORIZED FOR MERGE`: PR #970 is draft and
`UNSTABLE`, has no approving human review, `pr818-live-flow-freeze-target`
has a failed run, and Netlify preview statuses are pending. Required checks
`repo-forensics-pr-gate`, `unit_tests`, and `health_gate` passed at that
observed head, but those passes do not resolve the other conditions. This is
a time-bound status snapshot; it is not an approval or a merge authorization.

After merge, a later PR based on a commit that contains the trusted workflow
must exercise it. The repository owner must separately require the trusted
status in branch protection and verify that setting before treating it as a
merge gate. Until then, verifier output remains diagnostic and EVS-001 stays
incomplete.
