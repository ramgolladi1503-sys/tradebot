# ORB Owner Duplicate Visibility Audit

WORKTREE: `/Users/madhuram/tradebot-opening-range-retest-owner-integration`

SCOPE READ:
- `core/opening_range_retest_publication.py`
- `core/candidate_pool_orchestrator.py`
- `tests/test_opening_range_retest_owner_integration.py`
- `tests/test_opening_range_retest_emission_store.py`
- `tests/test_opening_range_retest_emission_store_adversarial.py`

STATUS: PROVEN

## Evidence Summary

- `core/opening_range_retest_publication.py` accepts only `opening_range_retest_v1`, requires `RAW_CANDIDATE` plus `READY_FOR_PUBLICATION`, and forwards a durable proposal to the store.
- `core/candidate_pool_orchestrator.py` treats `ACCEPTED_FOR_PUBLICATION` and `ALREADY_EMITTED` as the only accepted publication results.
- `OpeningRangeRetestEmissionStore.accept_candidate_proposal(...)` inserts exactly one lineage row and one outbox row on first acceptance, and returns `ALREADY_EMITTED` on an exact immutable match without inserting a second durable row.

## Observed Counts

| case | candidate_count | movement_candidate_count | owner_results | authoritative_count | existing_record_count | lineage rows | outbox rows | outbox state | publication_attempts | second authoritative exposure |
|---|---:|---:|---|---:|---:|---:|---:|---|---:|---|
| `ACCEPTED_FOR_PUBLICATION` | 1 | 1 | `["ACCEPTED_FOR_PUBLICATION"]` | 1 | 1 | 1 | 1 | `PENDING` | 0 | no |
| `ALREADY_EMITTED` on same store, second call | 0 | 0 | `["ALREADY_EMITTED"]` | 0 | 1 | 1 | 1 | `PENDING` | 0 | no |
| duplicate in same report | 1 | 1 | `["ACCEPTED_FOR_PUBLICATION", "ALREADY_EMITTED"]` | 1 | 2 | 1 | 1 | `PENDING` | 0 | no |
| same-process duplicate, sequential reports on same store | 0 | 0 | `["ALREADY_EMITTED"]` | 0 | 1 | 1 | 1 | `PENDING` | 0 | no |
| duplicate after store restart, new store same DB | 0 | 0 | `["ALREADY_EMITTED"]` | 0 | 1 | 1 | 1 | `PENDING` | 0 | no |

## Conclusion

No authoritative candidate exposure is created more than once.

- First acceptance creates the only authoritative ORB exposure for that `setup_id`.
- Same-report duplicates collapse to one visible candidate and one accepted outbox/lineage pair.
- Same-process sequential duplicates and restart duplicates do not re-expose the candidate at the report boundary.
- Outbox durability is singular: one `outbox:<setup_id>` row, one lineage row, and zero extra publication attempts until delivery starts.

## Test Anchor

This audit matches the assertions in:
- `tests/test_opening_range_retest_owner_integration.py`
- `tests/test_opening_range_retest_emission_store.py`
- `tests/test_opening_range_retest_emission_store_adversarial.py`
