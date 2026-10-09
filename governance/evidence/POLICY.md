# TradeBot Evidence and Verification Standard (report-only v1)

## Purpose and scope

This standard makes material engineering, mathematical, data, risk, research, and operational claims traceable through the existing Epic → Feature → Story/Bug/Task delivery lifecycle. It extends `core.delivery` work items and its append-only evidence records; it does not create another ledger, workflow state machine, runtime service, or trading authority.

The first rollout is **report-only**. Missing or incomplete legacy evidence is reported as `UNVERIFIED`; it is not silently upgraded and does not make CI claim that a check passed. A later change may make narrowly scoped checks blocking only after reviewing report results and false positives.

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

## Report-only CI and staged rollout

The PR workflow runs with `contents: read`, calculates changed paths against the PR base, checks material scopes and committed work-item records, emits a JSON artifact bound to the PR head SHA, and reports findings without blocking the PR. `--mode strict` is available for future opt-in enforcement; this workflow uses `--mode report-only`.

The Delivery Orchestrator owns the material path prefix matrix and must review it whenever a governed path is added, moved, or renamed. Changes to `VERIFICATION_MATRIX.json` require a matching coverage test and Evidence Standard review. The report-only workflow writes findings to both its JSON artifact and GitHub step summary; focused contract test failures still fail that workflow job. Record finding counts and focused CI durations from the exact-head report and summary, and have each reviewer record active review minutes. The capture protocol and initial pending state live in `ADOPTION_BASELINE.json`; the numeric baseline stays pending until a reviewed PR supplies measurements.

1. Audit current claims and retain `UNVERIFIED` where evidence has not been migrated.
2. Add records to new material work items and backfill the highest-risk inventory first.
3. Review report findings and false positives before proposing any blocking rule.
4. Certify critical subsystems independently. Installing this package is not certification.

The critical-component backfill remains deferred; the current legacy inventory is intentionally bounded and every listed legacy claim remains `UNVERIFIED` until its own evidence is accepted.

## Current limitations

- Legacy coverage is a bounded inventory, not a complete audit of every formula, algorithm, feed contract, risk rule, or performance claim.
- The workflow cannot determine whether an argument is scientifically persuasive or a source is authoritative.
- A local hash chain proves content integrity only, not author identity or external provenance.
- The initial CI report is informational and is not a merge-readiness signal.
- This standard does not change runtime behavior, risk limits, kill switches, feed freshness, buy-only execution rules, broker integrations, or strategy thresholds.
