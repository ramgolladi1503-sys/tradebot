# Rebootstrap V1 Review Evidence

## Bound source

Base SHA: `d5398f7ef19ca9b7f0cbbc07d8550e397f2123ef`

Forensic input established that the active release-store authority `93934d7c040b338b840eabd72e575644eaa3fbc0` is quarantined and that historical `aecec6...`, `071990...`, and `be002d...` do not establish a post-PR-907 primitive trust root. Existing history must therefore be retained but not trusted as an execution fallback.

## Implementation properties

- Adds an append-only schema-v2 `GOVERNED_REBOOTSTRAP` event.
- Preserves predecessor event and SHA as audit bindings.
- Forces `fallback_live_sha=null` and `rollback_status=NO_TRUSTED_FALLBACK`.
- Requires exact clean candidate, explicitly quarantined current head, complete dependency evidence, and the full 18-gate set.
- Uses independent rebootstrap verification before promotion.
- Prevents rebootstrap from a healthy/recovered authority.
- Fixes the normal verifier binding to include `dependency_graph_sha256`, matching the promotion binding contract.

## Validation status

`REPOSITORY_IMPLEMENTATION=COMMITTED_FOR_REVIEW`

The GitHub connector used to author this branch cannot execute repository pytest or mutation commands. Therefore:

`TEST_EXECUTION=NOT_RUN_IN_THIS_ENVIRONMENT`
`RECOVERY_MUTATION_CAMPAIGN=NOT_YET_IMPLEMENTED_22_OF_22`
`LIVE_RELEASE_STORE_MUTATION=NOT_PERFORMED`
`MORNING_CONTROLLER_RESUME=NOT_PERFORMED`

These are blockers to merge and to using the recovery path against the live release store. A reviewer/runtime with repository execution must run the required tests and add/execute the full recovery-specific adversarial campaign before promotion or merge.

## Safety / non-claims

```text
broker_write_authority=false
order_authority=false
paper_authorized=false
live_authorized=false
LIVE_EVIDENCE=NONE
EXECUTION_VIABILITY=NOT_CLAIMED
STRUCTURAL_EDGE_CERTIFICATION=NOT_CLAIMED
```
