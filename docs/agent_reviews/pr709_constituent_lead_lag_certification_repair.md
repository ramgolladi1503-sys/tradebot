# PR #709 Constituent Lead–Lag Certification Repair Review

## Agent Work Contract

Repair only the research and evidence-certification contracts for Constituent
Lead–Lag V1. Preserve the frozen strategy thresholds, existing raw Upstox
files, v1/v2 evidence directories, draft PR status and research-only boundary.

In scope:

- exact five-minute return-bar ownership;
- weighted/unweighted/coverage consistency;
- explicit session classifications;
- causal matched controls and numeric sensitivities;
- complete v3 freeze ownership;
- independent oracle reconciliation;
- focused and adversarial tests;
- truthful invalidation of the previous v2 certification.

Out of scope:

- broker, execution, feed, risk, live configuration or dashboard changes;
- strategy threshold tuning;
- production registration;
- raw-data redownload;
- PR merge;
- profitability or production-readiness claims.

## Scope Guard

Changed source is confined to `research/constituent_lead_lag/`, the associated
research scripts, focused tests and evidence/review documentation. No broker,
execution, risk, feed, manual-approval, live strategy registry, deployment or
production configuration file is part of this repair.

The implementation remains read-only research evidence:

- `is_order_action=false`
- `broker_api_called=false`
- `live_order_action=false`
- `broker_order_action=false`

## Grill Me Review

Assumption challenged: having the last three bars before a cutoff is equivalent
to having exact bars at `T-10m`, `T-5m` and `T`. It is not. Stale and gapped
constituent data could previously inflate both signal validity and coverage.

Claim challenged: an oracle `PASS` proved the v2 campaign. It did not. The old
oracle contained placeholder checks and did not independently reconcile the
freeze, artifact identities, exact coverage or final-verdict prerequisites.

Failure mode challenged: copied signal rows are not a matched control, and
string placeholders are not delayed-entry or concentration calculations.

Review outcome: the source-level contracts now address these defects, but the
real campaign result remains uncertified until a fresh v3 evidence bundle is
built from the preserved local data and the repaired oracle passes.

## Hermes Review

The repair does not alter live runtime behavior or cross protected execution
boundaries. Shared exact-bar ownership is intentionally centralized so weighted
signals, unweighted signals and membership coverage cannot silently use three
different definitions of availability.

No forbidden broker imports or order methods were introduced. Temporary GitHub
repair payload and workflow files were removed before the final source commit,
and the repository's original CI workflow was restored.

Review outcome: scope is appropriate for a draft research PR.

## GSD Review

Delivered:

- exact timestamp contract shared by all research lanes;
- explicit special/partial/complete session policy;
- real non-zero matched control construction;
- numeric delayed-entry and concentration calculations;
- complete v3 freeze and artifact-manifest ownership;
- independent oracle with PASS-first tamper tests;
- fail-closed legacy oracle compatibility;
- corrected PR and audit wording.

Evidence:

- complete six-module focused suite collected 48 tests;
- first run exposed one compatibility defect with 47 passing and 1 failing;
- the compatibility defect was repaired without weakening v3 certification;
- the identical focused command then passed on GitHub's runner.

Next action: build `proxy_campaign_2024_2025_v3` on the machine that owns the
preserved external campaign files, then run the repaired oracle.

Delivery outcome: ACCEPTED FOR DRAFT RESEARCH REPAIR, NOT ACCEPTED AS A FINAL
REAL-DATA STRATEGY VERDICT.

## QA / Safety Review

Negative and adversarial coverage includes:

- missing cutoff, `T-5m` and `T-10m` bars;
- stale/non-contiguous bar sequences;
- exact weighted/unweighted parity;
- coverage identity and numeric reconciliation;
- copied-control rejection;
- numeric delay and concentration fixtures;
- valid oracle fixture followed by independent hash, summary, state, coverage
  and verdict-prerequisite tampering;
- legacy evidence bundles remaining non-certifiable.

Research outputs continue to set non-action fields false and carry no route to
broker or order execution.

## Acceptance Proof

Source-level acceptance requires:

1. the complete PR-focused test command passes;
2. Minerva classifies changed tests as behavioral/evidence proof rather than
   fake-confidence or shape-only tests;
3. Cerberus confirms explicit non-action defaults;
4. temporary repair files are absent;
5. PR #709 remains draft, open and unmerged;
6. v2 certification language is invalidated rather than preserved.

Real-data certification additionally requires a new v3 bundle, full frozen
hash reconciliation, at least 95% exact-bar dual coverage where applicable and
an independent oracle `PASS`.

## Runtime Proof Required After Merge

No merge is authorized by this review. This is a research-only branch and has
no live runtime integration.

Before any future promotion, separately prove that no strategy registry,
broker, execution, feed, risk, dashboard or deployment path imports or consumes
these research modules. That proof is outside the present PR.

## What This PR Does Not Prove

This PR does not prove:

- a profitable structural edge;
- positive or negative out-of-fold economics;
- production readiness;
- commercial usability of the community-weight dataset;
- that the previous v2 counts, coverage, reasons or signal totals remain valid;
- that `NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT` is the final result.

The truthful current evidence taxonomy is
`PROXY_EVALUATION_FAILED_DATA_CONTRACT` until v3 is produced and certified.

## Human Approval

Human approval for merge or strategy promotion has not been granted. Keep PR
#709 draft and unmerged. A human must review the v3 persisted evidence and
oracle report before selecting any final strategy taxonomy.
