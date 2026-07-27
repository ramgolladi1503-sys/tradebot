mode: RESEARCH_ONLY_PROVENANCE_AUDIT
candidate_id: signal_ledger_provenance_v1
decision: SIGNAL_LEDGER_INVALIDATED
reason: The audited bytes are an exact 24-row multi-owner blocked-placeholder inventory. Git history dynamically proves the ledger and sidecar were introduced with the historical placeholder generator at commit 686af0fe, while the inventory has prior immutable lineage and was present at that commit. Historical generator execution and an independent reconstruction reproduce the exact ledger bytes. The immutable invalidation record directly invalidates the generator implementation; direct ledger-hash invalidation remains unresolved, while ledger invalidation is derived through the proven generator-to-ledger and historical-to-current byte chain.
timestamp: 2026-07-25T03:00:01+05:30
research_only: true
read_only: true
broker_api_called: false
is_order_action: false
allowed_for_live_execution: false
outcomes_read: false
pnl_read: false
holdout_outcomes_read: false
source: Immutable Git history and blobs, the committed ledger and sidecar, the historical generator and inventory, the implementation-invalidation record, and two independent full-history evidence builds

# Signal-Ledger Ownership and Provenance Evidence v1

## Agent Work Contract

Audit immutable ownership and provenance for `signal_ledgers_v4_2/signal_ledgers.json`, physical SHA-256 `b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed`, 24 rows. No strategy execution, outcome inspection, P&L, replay, WFA, tuning, or holdout evaluation is permitted.

## Scope Guard

Evidence is limited to Git history and blobs, the committed ledger and sidecar, the historical placeholder generator and inventory, the immutable implementation-invalidation record, and explicitly recorded non-outcome metadata searches. Self-generated provenance-package files, this Agent Review, its tests, temporary workflow, and Code Excellence reports are excluded from provenance-search findings.

## Grill Me Review

All 24 rows are blocked placeholders: `status=SIGNAL_INPUT_DATA_MISSING`, `blocker=NO_SIGNAL_LEDGER_SOURCE`, and blank implementation, parameter, dataset, temporal, and fold fields. The artifact is not a collection of executed trading signals.

## Hermes Review

The audit separates embedded owner labels, canonical strategy mapping, aggregate ownership, historical generator identity, strategy implementation authority, parameters, datasets, temporal ordering, split/fold, freeze, contamination clearance, and invalidation authority.

## GSD Review

The primary path discovers ledger and sidecar introduction dynamically and permits proven prior inventory lineage. It hashes historical Git blobs, executes the historical generator, and independently reconstructs expected output bytes. A separate oracle independently derives history, blobs, output binding, invalidation lineage, and non-outcome search counts without consuming the primary evidence dictionary or primary search helper.

## QA / Safety Review

- `research_only=true`
- `read_only=true`
- `broker_api_called=false`
- `is_order_action=false`
- `allowed_for_live_execution=false`
- `outcomes_read=false`
- `pnl_read=false`
- `holdout_outcomes_read=false`

## Acceptance Proof

- Audited ledger: 24 rows, SHA-256 `b9736aa6af68a07c32a01dbc2bc60220acf8337181e3878940abfab540398bed`.
- Ledger, sidecar, and placeholder generator introduction: dynamically discovered commit `686af0feff7a4485ebe4e249cb498b33d649a5cd`.
- Introduction status: `PROVEN_WITH_PRIOR_LINEAGE`; the historical inventory predates the ledger and is present at the introduction commit.
- Historical ledger Git blob: `b8b9b8e9b9cfc53122ef01126a6817d7bcb5a4d2`.
- Historical sidecar Git blob: `e5e221c6e0d8d19dc05a1839efbf4f7fe2e5aa47`; its digest matches the historical ledger.
- Historical generator Git blob: `935bdbdf30a461e290ee3566ac7e5e3e859e271b`.
- Historical inventory Git blob: `976872766598486f2150c3008a79b07ea634c887`.
- Historical generator execution and independent reconstruction reproduce the exact committed ledger bytes and SHA-256.
- Embedded owner labels: 24 proven fields; 18 map to counted historical strategy IDs and six remain historical hypothesis labels. Aggregate canonical strategy owner is null.
- Strategy implementation, parameters, dataset, temporal ordering, split/fold, pre-outcome freeze, and contamination clearance remain unresolved.
- Direct ledger-hash invalidation: `UNRESOLVED`; the immutable invalidation file does not contain the ledger hash.
- Implementation invalidation: `CONFIRMED`; it identifies commit `686af0fe...` and the placeholder generator path.
- Derived ledger invalidation: `CONFIRMED` with reason `DERIVED_THROUGH_PROVEN_INVALIDATED_GENERATOR_BINDING`.
- Primary/oracle agreement: `AGREEMENT` on physical hash, row count, introduction history, blobs, generator binding, ownership, invalidation levels, scoped search counts, and verdict.
- Two independent full-history builds are byte-for-byte and semantically identical.
- Final verdict: `SIGNAL_LEDGER_INVALIDATED`.

## Runtime Proof Required After Merge

None. This is research evidence only and grants no paper or live authority.

## What This PR Does Not Prove

It does not prove real signals, strategy correctness, parameter authority, dataset lineage, causal timestamps, fold identity, freeze authority, contamination clearance, profitability, replay validity, WFA, paper readiness, or live readiness.

## Human Approval

Human approval is required before any replacement ledger generation or later authority decision. The invalidated v4.2 placeholder ledger must not be promoted.

## Validation

- Focused provenance tests: `22 passed in 1.77s`
- Full option-E2E tests: `166 passed in 85.83s (0:01:25)`
- Evidence manifest semantic SHA-256: `2d5d6bcb62909e9a6763314be9779a823ec36dd817d6faeac03c5aa5b91cc872`
