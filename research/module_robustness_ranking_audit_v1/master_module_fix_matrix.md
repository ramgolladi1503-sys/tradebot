# Master Module Fix Matrix

See `master_module_fix_matrix.csv` for all modules. Material findings:

- F-P0-001 (P0, VERIFIED): Primary checkout was dirty at audit start, so a trustworthy baseline could not be established from the working tree itself.
- F-P1-001 (P1, VERIFIED): The canonical ranking layer exists, but UI fallback paths can display rows from visible/executable filters when top ranked snapshots are empty.
- F-P1-002 (P1, PARTIALLY_VERIFIED): Score/confidence semantics are heuristic setup scores, not calibrated predictive probabilities.
- F-P1-003 (P1, VERIFIED): Fallback, stale, subscription-failed, and price-mismatch quote truth can block executable status, but policy is split across scoring, ranking, executable truth, and top-opportunity truth modules.
- F-P2-001 (P2, VERIFIED): Many modules have no direct semantic test signal in static inventory.
- F-P2-002 (P2, PARTIALLY_VERIFIED): Ranking determinism is partially verified for a synthetic frozen input but not for full replay/runtime evidence.
- F-P3-001 (P3, VERIFIED): Generated/runtime/static exclusions are explicit and counted, but excluded runtime evidence was not semantically audited module-by-module.
