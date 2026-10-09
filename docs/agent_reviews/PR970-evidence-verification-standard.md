# PR970 Evidence Verification Standard Review

## Enforcement follow-up

The verifier now has an `enforce-new-material` mode: structural `ERROR`/`BLOCKING` findings and material paths without a current covering work item fail the command, while explicit `UNVERIFIED` claim findings remain warnings. For current material records it also requires complete Definition of Ready fields, G0/G1/G2/G3/G4/G5/G7 lifecycle evidence, distinct lifecycle role authors where the existing orchestrator checks them, traversal of required state-history stages, and a pre-merge state of `RELEASE_READY`, `PR_OPEN`, or `CI_GREEN`. G6 is omitted because this check runs within PR CI and cannot require its own completed result in advance. PR CI invokes this mode against exact base/head refs and uploads the resulting report. Report-only remains available for diagnosis; strict mode retains its all-findings-block behavior.

The candidate matrix is checked against a required material-prefix set, and regression tests remove each required prefix in turn. This closes that specific bypass only when the verifier containing the check is trusted. The current candidate PR still supplies its own workflow, verifier, and policy; it can propose weakening those controls together. The independent audit found an existing trusted-base exact-SHA workflow pattern, but `main` does not yet contain a trusted evidence workflow. This PR cannot make a newly added base-authoritative workflow execute for itself. A controlled bootstrap followed by a required stable check is still necessary.

This provides a repository PR-diff check only; it is not yet an independently trusted merge gate. It does not intercept every request sent through Codex, ChatGPT, Claude, or another platform. The intake audit found only downstream PR-time automation; Codex prompts, GitHub issues, local/CLI/MCP work, manual Actions, and other platform requests lack a common fail-closed intake hook. Universal task coverage is `UNSATISFIED`. Classic branch protection requires `repo-forensics-pr-gate`; the active main ruleset requires `unit_tests` and `health_gate`. Neither requires `Enforce new material evidence coverage`. This work does not mutate external repository settings. The check grants no merge, research, or runtime authority.

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
