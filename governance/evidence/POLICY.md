# TradeBot Evidence and Verification Standard

## Purpose and scope

This standard makes material engineering, mathematical, data, risk, research, and operational claims traceable through the existing Epic → Feature → Story/Bug/Task delivery lifecycle. It extends `core.delivery` work items and its append-only evidence records; it does not create another ledger, workflow state machine, runtime service, or trading authority.

The repository PR gate blocks new material changes that lack a current work-item evidence record, blocks structural validation errors, and blocks changed paths that are neither classified as material nor covered by a trusted non-material exemption. Explicit `UNVERIFIED` legacy and current claims remain warnings; they are never upgraded by this gate. Candidate changes cannot exempt their own paths. This is repository-side PR enforcement only. It cannot intercept every request sent through Codex, ChatGPT, Claude, or another task platform. Universal task-intake enforcement remains `UNSATISFIED` until each platform has a verified integration that creates or links a work item before substantive work.

## Four evidence gates

These evidence gates are named `G1_SOURCE`, `G2_CORRECTNESS`, `G3_ADVERSARIAL`, and `G4_INDEPENDENT`. They are separate from the existing delivery state gates `G0_REQUIREMENT` through `G9_PRODUCTION_VERIFY`.

| Evidence gate | Question | Existing delivery owner | Minimum evidence |
|---|---|---|---|
| G1 Source | What requirement, specification, derivation, or dataset supports the proposed behavior? Which assumptions are empirical or theoretical? | Product Owner / Business Analyst / Architect / Quant Research Architect | Registered source IDs, explicit assumptions, and a hash-sealed `SOURCE_VERIFICATION_EVIDENCE` record. |
| G2 Correctness | Does the implementation satisfy the stated contract at normal, boundary, and failure conditions? | QA Engineer / Senior QA, distinct from the developer | `CORRECTNESS_VERIFICATION_EVIDENCE` with reproducible checks or reference comparisons. |
| G3 Adversarial | What independent baseline, counterexample, stale/corrupt input, or fault condition was used to challenge it? | QA Engineer / Senior QA, separate reviewer identity | `ADVERSARIAL_VERIFICATION_EVIDENCE` recording the attack and result. |
| G4 Independent | Does the evidence support the exact claim and exact candidate/data/configuration? What remains unproven? | UAT Reviewer / Release Manager / Production SRE / Quant Research Architect | `INDEPENDENT_EVIDENCE` with artifact references and exact subject commit for a `VERIFIED` claim. |

The work-item record carries claim IDs, source IDs, typed assumptions (`PUBLISHED_FACT`, `THEORETICAL_ASSUMPTION`, or `EMPIRICAL_HYPOTHESIS`), status, limitations, and references to the existing sealed evidence records. A published fact requires a registered source. `validate_work_item` checks the contract; `tools/verify_evidence.py` checks registries, source locators, changed-path coverage, and commit binding. Hashes protect integrity and linkages; they do not authenticate a source, reviewer identity, or scientific judgment.

## Claim statuses and applicability

- `VERIFIED`: a reviewer-declared status that requires all four gate evidence records, `PASS` results, expected evidence types and permitted delivery roles, distinct asserted reviewer identities, registered sources, and candidate binding. The local validator checks structure and SHA-256-shaped references; it does not read referenced artifacts to verify their bytes or authenticate reviewer identity. CI therefore reports the assessed status as `UNVERIFIED` with `verification_level=STRUCTURAL_ONLY` until those artifacts and reviewers are independently accepted.
- `UNVERIFIED`: required evidence is absent, incomplete, stale, or not independently reviewed. This is the initial status for audited legacy areas.
- `CONTRADICTED`: evidence or a controlled challenge conflicts with the claim. Preserve the negative result and its reference.
- `NOT_APPLICABLE`: the work item or claim does not apply; include a reason and a reference to known work-item evidence (claim-level records may also cite a registered source). It is not equivalent to `VERIFIED`.

For a material work item, `extensions.evidence_standard` must set `enforcement_mode` to `REPORT_ONLY`, state applicability, list assessed paths, and list claims. Each claim must state `claim_id`, `statement`, `claim_kind`, `status`, `source_ids`, `assumptions`, `gate_evidence`, and `limitation`. A `NOT_APPLICABLE` claim also needs `evidence_refs` identifying a known source or evidence record. A `VERIFIED` declaration requires a full four-gate chain. Its exact subject is bound by the CI report's candidate SHA plus work-item contract and evidence hashes; embedding the containing commit SHA in the same commit would be self-referential. The report checks that its code, registries, source files, matrix, and work-item records match the candidate tree. An unresolved or contradicted claim stays visible and cannot be described as a pass.

## Claim classes and prohibited inference

Engineering correctness, operational reliability, predictive validity, and profitability are distinct claim kinds. Passing tests support only the behavior those tests exercise. It does not establish strategy edge, profitability, live readiness, or broker behavior. Strategy and performance claims require the separate research-validation and release certification processes, including provenance, chronological controls, realistic costs, and protected holdouts where applicable. This standard does not reopen restricted holdout data.

Authentication and security claims use applicable security specifications and operational fault tests; they do not require a trading backtest. Source selection is feature-specific. External sources must be independently reviewed before their registry status is `VERIFIED`; this offline checker only resolves local repository paths and never fetches or blesses an external URL.

## Ownership and separation of duties

Use the existing role definitions in `docs/tradebot_delivery/ORGANIZATION.md`. Developers may provide implementation evidence but cannot author G2/G3/G4 evidence for their own work. G2, G3, and G4 evidence must have distinct author identities. Role and author fields are assertions in the local work item; independent identity is not cryptographically authenticated by this tool. GitHub review and CI identity remain separate proof sources.

The existing Product Owner + BA, Architecture + Developer, QA + Senior QA, UAT + Release Manager workflow owns the corresponding gates. An independent reviewer must not approve their own implementation. No delivery transition, merge approval, strategy certification, or execution permission is created by an evidence report.

## Per-claim report mode and material-path enforcement

Per-claim evidence assessment remains report-only: declaring a claim `UNVERIFIED` is visible but is not itself a blocking error. The trusted workflow `frozen-head-exact-sha-certification.yml` uses `pull_request_target` to run the verifier and delivery modules checked out at the exact PR base SHA. It fetches the PR head and materializes a tar archive of the candidate commit as a separate data tree, avoiding Git checkout filters from candidate metadata. It passes that tree through `--candidate-root`; candidate Python, tests, and workflow definitions are not executed by the trusted job. The report records and checks both `verifier_source_sha` and `candidate_root_sha`; each parsed file is also byte-compared to its blob at the exact candidate SHA. Candidate paths that traverse symlinks are rejected before reading.

The trusted verifier calculates changed paths against the exact base and head, checks material scopes and committed work-item records, emits a JSON artifact bound to the PR head SHA, and fails on structural `ERROR` findings, explicit `BLOCKING` findings, uncovered new material paths, and unclassified changed paths. A path is classified as material by the candidate matrix only when that scope is also present in the work item's assessed paths and registered claim scope. A path outside those material scopes must match an explicit exemption read from the verifier's trusted base tree; each exemption requires a non-empty rationale and owner and cannot overlap a protected material scope. The candidate matrix must exactly preserve the base's `protected_material_path_prefixes` and trusted exemptions, so candidate code cannot remove a protected floor or exempt its own changed path. An unclassified path blocks until a reviewed change adds it to material scopes. The protected floor is stored in `VERIFICATION_MATRIX.json` and loaded from the verifier checkout (`ROOT`), not from `--candidate-root`.

Full reports may contain candidate-controlled paths and finding details. Trusted CI callers must pass `--output` and retain the resulting JSON artifact; stdout and the GitHub step summary contain only safe status, counts, severities, and finding codes. Direct invocations without `--output` intentionally emit only that safe summary and print a notice that the structured report was omitted. To retain auditable details during local diagnosis, pass `--output <path>`.

Current material scopes include `.github/workflows/ci.yml`, `.github/workflows/tests.yml`, `tests/delivery/`, and `docs/agent_reviews/`. The last scope covers both changed review documents in this candidate diff. `UNVERIFIED` remains non-blocking and is reported distinctly from path-classification failures. The trusted verifier reads `enforcement_stage` from the candidate matrix; `--mode enforce-new-material` fails closed unless that candidate declares `BLOCK_NEW_MATERIAL`. `--mode report-only` remains available for local diagnosis, and `--mode strict` blocks on any finding. The separate `evidence-gates.yml` job executes candidate code for diagnostics in the ordinary `pull_request` context and is explicitly named `Candidate-code evidence diagnostics (untrusted)`; its workflow and step identify it as advisory and its report-only mode is not the trusted merge-evidence status.

This PR adds the trusted workflow, but `pull_request_target` takes its workflow definition from the PR base. Therefore this workflow cannot protect the PR that first adds it; a later PR based on a commit containing the workflow is the first one it can check. The current classic branch protection requires `repo-forensics-pr-gate`; the active main ruleset requires `unit_tests` and `health_gate`. Neither requires the trusted status `Trusted base evidence coverage`. Branch-protection enforcement remains `UNSATISFIED` until an authorized ruleset update is read back and proves that exact status is required. Until then, a failing check does not block merge. This change does not mutate external repository settings.

The Delivery Orchestrator owns the material path prefix matrix and must review it whenever a governed path is added, moved, or renamed. Changes to `VERIFICATION_MATRIX.json` require a matching coverage test and Evidence Standard review. New or unclassified paths block until material coverage is added; only the trusted base policy can grant a non-material exemption, with rationale and owner. The evidence workflow writes findings and blocking counts to both its JSON artifact and GitHub step summary. Record finding counts and focused CI durations from the exact-head report and summary, and have each reviewer record active review minutes. The capture protocol and initial pending state live in `ADOPTION_BASELINE.json`; the numeric baseline stays pending until a reviewed PR supplies measurements.

1. Audit current claims and retain `UNVERIFIED` where evidence has not been migrated.
2. Add current records to every new material PR change; uncovered paths fail the evidence check.
3. Confirm branch protection requires this exact stable check name; repository code cannot enforce its own branch-protection setting.
4. Certify critical subsystems independently. Installing this package is not certification.

The critical-component backfill remains deferred; the current legacy inventory is intentionally bounded and every listed legacy claim remains `UNVERIFIED` until its own evidence is accepted.

## Current limitations

- Legacy coverage is a bounded inventory, not a complete audit of every formula, algorithm, feed contract, risk rule, or performance claim.
- The workflow cannot determine whether an argument is scientifically persuasive or a source is authoritative.
- A local hash chain proves content integrity only, not author identity or external provenance.
- The CI check covers governed repository PR diffs only; it is not a task-platform intake interceptor.
- Until each task platform is integrated, a request that cannot be linked to a durable work item is `UNSATISFIED` for universal process compliance.
- Branch-protection enforcement remains `UNSATISFIED` until settings readback proves the evidence check is required; a workflow existing in the repository does not prove the setting is active.
- Only `scripts/submit_agent_work.py` and supervisor `preflight`/`claim` currently enforce committed-work-item admission. Their payload must identify a tracked canonical item by ID, exact-byte SHA-256, and embedded task-contract ID; the request must exactly match that task contract's source, action, title, scope, and path lists. Missing, dirty, stale, malformed, or mismatched records fail closed. This is not universal task intake.
- Caller-provided `--approve` and `--approved-by` values are unauthenticated assertions. Medium/high-risk CLI patch work remains blocked until an authenticated approval mechanism is independently implemented and verified.
- The repository inventory identifies 18 active `workflow_dispatch` workflows, each `UNSATISFIED` for pre-work admission. The PR818 test-only auto-write workflow is retired; PR #823 merged on 2026-08-15. Direct GitHub dispatch trust remains `UNSATISFIED`.
- The PR818 freeze workflow now compares only the exact PR base-to-head delta against its frozen production and governance path lists. Removing the old pinned-baseline-to-PR-base comparison removes detection of pre-existing drift already present on main. Protected changes introduced by the PR still fail, and the exact bootstrap exception remains. This change does not attest that main itself matches the older baseline.
- This standard does not change runtime behavior, risk limits, kill switches, feed freshness, buy-only execution rules, broker integrations, or strategy thresholds.
