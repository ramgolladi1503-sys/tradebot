mode: RESEARCH_ONLY_PROVENANCE_AUDIT
candidate_id: signal_ledger_provenance_v1
decision: SIGNAL_LEDGER_INVALIDATED
reason: Immutable Git history proves the 24-row artifact is a multi-owner blocked-placeholder inventory generated at commit 686af0fe, and a later hash-linked repository record explicitly invalidates that v4.2 evidence implementation.
timestamp: 2026-07-25T03:00:01+05:30
research_only: true
read_only: true
broker_api_called: false
is_order_action: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: Immutable repository history, hash-protected ledger content, declared non-outcome external evidence roots, and two independent durable audit runs

# Signal-Ledger Ownership and Provenance Evidence v1

## Agent Work Contract

This task audits immutable ownership and provenance for the physical artifact `research/option_e2e_recertification_v4/signal_ledgers_v4_2/signal_ledgers.json`, SHA-256 `b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed`, 24 rows. It does not execute strategies or inspect outcomes.

## Scope Guard

The implementation reads the ledger, its sidecar, Git objects and history, its historical generator and inventory, the repository invalidation record, and non-outcome closure evidence. It does not read outcome or P&L artifacts and does not run replay, WFA, holdout evaluation, tuning, broker, order, feed, risk, dashboard, or strategy-registration paths.

## Grill Me Review

The artifact name overstates its content. All 24 records have `status=SIGNAL_INPUT_DATA_MISSING`, `blocker=NO_SIGNAL_LEDGER_SOURCE`, and blank implementation, parameter, source, temporal, and fold fields. The hash protects the embedded row owners, but those rows are blocked placeholders and not generated trading signals. Determinism does not create authority.

## Hermes Review

The audit keeps ownership, generator implementation, strategy implementation, parameters, dataset, temporal ordering, split/fold, freeze, and contamination authority separate. A Git commit that atomically introduces a placeholder generator and its output proves which generator created the bytes; it does not prove that any named strategy implementation generated a signal.

## GSD Review

The primary evaluator and independent oracle separately verify physical hash, row count, embedded owners, immutable generator binding, missing provenance layers, contamination evidence state, and historical invalidation. Publication fails closed on semantic disagreement.

## QA / Safety Review

Every compact artifact records:

- `research_only=true`
- `read_only=true`
- `broker_api_called=false`
- `is_order_action=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`

No production or high-risk path was modified.

## Acceptance Proof

Sources searched and findings:

- Exact ledger and sidecar: physical hash and 24-row count match.
- Git history: commit `686af0feff7a4485ebe4e249cb498b33d649a5cd` atomically introduced the generator and exact ledger bytes.
- Generator: `build_signal_ledgers.py`, Git blob `935bdbdf30a461e290ee3566ac7e5e3e859e271b`, content SHA-256 `6505aa49f008e98b395c81530c006e3712fdb575451b650be583fe89cdd0034b`.
- Historical inventory: Git blob `976872766598486f2150c3008a79b07ea634c887` supplied 18 counted strategies; the generator appended six hardcoded research hypotheses.
- Embedded owners: 24 distinct strategy or hypothesis IDs are protected by the ledger physical hash. Ownership is `PROVEN_WITH_LIMITATIONS` for individual placeholder rows; the aggregate ledger has no single canonical strategy owner.
- Implementation: the placeholder generator is proven, but no strategy implementation commit or hash is bound to any row.
- Parameters and dataset: all row parameter and source hashes are blank; no ledger-bound parameter or dataset manifest was found.
- Temporal and split: feature cutoff, signal, legal-entry, and fold fields are blank. The literal session value `frozen` and `is_holdout=false` are not treated as freeze or split proof.
- Freeze and contamination: no hash-bound pre-outcome freeze manifest or immutable contamination-clearance record was found. Outcomes and P&L were not read, so all four contamination-clearance states remain `UNRESOLVED`.
- Historical invalidation: `v4_2_evidence_implementation_invalidation.json`, SHA-256 `8d1b8d7cc264b92bf1499ede393b5ed3ec1220419c2fc031039717b67400a1b0`, binds the invalid decision to commit `686af0fe...` and the generator path.
- Durable runs: `/Users/madhuram/tradebot-ml-evidence/all-strategy-option-e2e-recertification-v4/signal_ledger_provenance_v1/20260725-030000_run_a` and `20260725-030001_run_b`.
- Semantic determinism: both runs have semantic manifest SHA-256 `52b4c6bffd23a2a9708cdc6af0bfa63a5fe44127ea92a3d5744a125a2a70617a`.
- Primary/oracle result: `AGREEMENT` on every declared semantic check.
- Final verdict: `SIGNAL_LEDGER_INVALIDATED`.

## Runtime Proof Required After Merge

None. This evidence is research-only and grants no runtime, paper, or live authority.

## What This PR Does Not Prove

This work does not prove real signals, strategy correctness, parameters, dataset lineage, causal timestamps, split or fold identity, pre-outcome freeze, contamination clearance, profitability, replay validity, paper readiness, or live readiness. It does not convert any ledger into canonical signal authority.

## Human Approval

Human approval remains required for any later research execution or authority decision. The invalidated artifact must not be promoted or used as a substitute for newly generated pre-outcome evidence.
