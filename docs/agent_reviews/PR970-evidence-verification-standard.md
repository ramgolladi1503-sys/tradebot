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
The inventory lists 18 active `workflow_dispatch` workflows, all
`UNSATISFIED` for pre-work admission, plus the retired PR818 auto-write
workflow. PR #823 is recorded as merged on 2026-08-15. Universal platform
intake, direct GitHub dispatch trust, branch protection, and authenticated
human approval remain `UNSATISFIED`.

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

The PR818 auto-write workflow is deleted because its completed test-only repair
was merged in PR #823; no other workflow-dispatch workflow is retired. No branch
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
