# Strategy Truth Phase 3B Owner Integration

IMPLEMENTATION DIRECTION: RIGHT_WITH_GAPS

WORKTREE: /Users/madhuram/tradebot-opening-range-retest-owner-integration

BRANCH: fix/opening-range-retest-owner-integration

APPROVED OBJECTIVE: Connect the truthful `READY_FOR_PUBLICATION` temporal proposal for `opening_range_retest_v1` to a durable owner-acceptance path so the system exposes exactly one authoritative candidate only after durable acceptance, without changing strategy formulas, thresholds, completed-history semantics, ranking, TradeBuilder, Phase 1, Phase 2, broker, or execution code.

WHAT WAS ACTUALLY IMPLEMENTED: Added a narrow publication helper that builds an `OpeningRangeRetestProposal` from the raw temporal candidate identity and semantic fingerprint, then integrated that helper into `core.candidate_pool_orchestrator.build_candidate_pool_report` as an optional owner-acceptance boundary for `opening_range_retest_v1`. The orchestrator now records owner outcomes in report metadata, suppresses blocked owner states, and preserves one authoritative candidate only when the owner store accepts or already recognizes the setup. Added direct integration tests for accept, duplicate, restart, duplicate-within-run, blocked-state containment, and concurrency semantics.

ARCHITECTURE CHANGE: NECESSARY_MINIMAL

STARTING COMMIT: 32e658836280bff51e952e30931a5fb0692c87ba

FINAL IMPLEMENTATION HEAD BEFORE EVIDENCE COMMIT: 32e658836280bff51e952e30931a5fb0692c87ba

FILES CHANGED:
- `core/candidate_pool_orchestrator.py`
- `core/opening_range_retest_publication.py`
- `tests/test_opening_range_retest_owner_integration.py`

SOURCE / ANCESTRY:
- temporal head: `d0bb88ad631965e9b3ba6f43d09a4cbf06f669e1`
- owner foundation head: `863ad70b9ad513be0a058926129afd8ae1d5000a`
- merge-base between temporal and owner lines: `8a5e3974459c5011759bb2eef7ba6b1012d2bce2`
- integration worktree head before evidence commit: `32e658836280bff51e952e30931a5fb0692c87ba`

OWNER / PUBLICATION BOUNDARY:
- `core/opening_range_retest_publication.py` turns the raw temporal candidate into a durable `OpeningRangeRetestProposal`.
- The proposal fingerprint is semantic and stable: `strategy_id`, `direction`, `status`, `raw_score`, `entry_trigger`, `invalid_if`, `rank_reason`.
- The publication helper preserves `setup_id`, `history_hash`, and `proposal_ready_at_iso` from the temporal candidate evidence.
- `core/candidate_pool_orchestrator.build_candidate_pool_report(...)` is the only integration point; the strategy callable itself remains unchanged.

OWNER BEHAVIOR:
- accepted: pass
- duplicate after restart: pass
- duplicate within a single report: pass
- owner busy: pass
- owner unavailable: pass
- owner state conflict: pass
- concurrency: pass
- blocked owner states do not abort unrelated generators: pass

AUTHORITY SEMANTICS:
- raw temporal candidate remains `RAW_CANDIDATE`
- owner acceptance is durable and explicit
- report metadata now carries `opening_range_retest_owner_results`
- blocked owner states are surfaced as warnings/blockers and do not become exposed candidates
- `ALREADY_EMITTED` is treated as an authoritative existing record, not a new duplicate exposure

SETUP FINGERPRINT:
- strategy id: `opening_range_retest_v1`
- direction: `BUY_CALL`
- status: `RAW_CANDIDATE`
- raw score: `0.451504`
- entry trigger: `opening_range_breakout_retest_hold`
- invalid if: `price_returns_inside_opening_range`
- rank reason: `opening range breakout retest held`

OWNER FINGERPRINT:
- accepted proposal setup id is preserved from the temporal evidence
- history hash is preserved
- proposal-ready timestamp is preserved
- owner record remains stable across restart
- same setup in the same report is exposed once

DIRECT INTEGRATION TESTS:
- `tests/test_opening_range_retest_owner_integration.py`

FOCUSED TEST RESULT: `55 passed in 33.89s`

RELATED SUITE RESULT: `185 passed in 11.97s`

FULL-SUITE RESULT: `5928 passed, 1 failed, 1 deselected, 934 warnings in 427.74s`

FIRST FAILURE:
- `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
- failure text: `RuntimeError: [AUTH] missing_kite_access_token`
- this failure does not involve `opening_range_retest_v1`, the owner store, or the owner integration code

KNOWN AUTH FAILURE: present and accepted as pre-existing

OPENING-RANGE FAILURES: zero

GENERATED ARTIFACTS DURING VERIFICATION:
- `runtime/strategy_validation/regime_timeline.jsonl` picked up generated timeline lines during the suite and was restored to `HEAD`
- three `MagicMock`-named files were created during verification and removed before commit

BEHAVIOR CHANGED:
- owner publication is now enforced at the candidate-pool boundary for `opening_range_retest_v1`
- blocked owner states now suppress candidate exposure instead of leaking an unauthoritative proposal downstream
- report metadata now carries owner outcomes

BEHAVIOR PRESERVED:
- strategy callable logic and thresholds
- completed-history temporal semantics
- raw temporal candidate fingerprint
- phase-2 downstream enrichment behavior for non-owner paths
- unrelated generators and report behavior
- no broker, order, execution, or risk path changes

CLAIM BOUNDARY:
- This work proves durable-owner integration, not profitability, ranking superiority, execution readiness, or live readiness.
- The code path now exposes the temporal proposal only after durable acceptance, but that is not a production certification claim.

EVIDENCE STATUS: PROVEN

REMAINING GAPS:
- The orchestrator now has a deliberate durable-owner side effect for `opening_range_retest_v1`; this is narrow and intentional, but it means the report builder is no longer side-effect free with respect to the owner store.
- The repository-wide suite still has the known unrelated auth failure and is not green.

ROLLBACK:
- Remove the optional owner-store hook from `core.candidate_pool_orchestrator.py`
- delete `core/opening_range_retest_publication.py`
- remove `tests/test_opening_range_retest_owner_integration.py`
- restore `build_candidate_pool_report` to the prior pure report-building behavior

EXPLICIT NON-CLAIMS:
- no strategy formulas changed
- no strategy thresholds changed
- no completed-history semantics changed
- no ranking logic changed
- no TradeBuilder change
- no broker, order, execution, or risk change
- no historical validation or profitability claim
- no live readiness claim
