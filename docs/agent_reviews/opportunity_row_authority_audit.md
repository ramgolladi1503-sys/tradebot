IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Prove authoritative row provenance for canonical strategy dashboard opportunities without changing strategy logic, ranking, Phase 2 decisioning, thresholds, or reader-facing aliases.

WHAT WAS ACTUALLY IMPLEMENTED:
I added explicit provenance stamping for canonical ranked-snapshot rows and live Phase 2 rows, and I added focused tests that prove the authority fields on executable, advisory, and blocked dashboard rows. The canonical ranked snapshot path now stamps `pipeline_source=CANONICAL_RANKED_SNAPSHOT`, `status_authority=CANONICAL_CANDIDATE_POOL`, and `rank_authority=CANONICAL_RANKING`. The live Phase 2 path now stamps `pipeline_source=LIVE_PHASE2`, `status_authority` from the live truth context when present, and `rank_authority=LIVE_PHASE2_RANKING` on all projected rows. The dashboard reader still preserves the canonical alias keys and normalizes top-opportunity payloads through the truth contract.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

VERDICT:
OPPORTUNITY_ROW_AUTHORITATIVE_PROVENANCE_PROVEN

STARTING HEAD:
`9735a67f6faaf56ae72da2b90ae9ef3e9e3ef36b`

FINAL HEAD:
pending commit

FILES CHANGED:
- `core/top_opportunity_executable_truth.py`
- `core/canonical_ranked_ui_adapter.py`
- `core/orchestrator.py`
- `tests/test_ranked_pipeline_runtime_evidence_wiring.py`
- `tests/test_runtime_execution_truth_evidence.py`
- `docs/agent_reviews/opportunity_row_authority_audit.md`

CANONICAL RANKED-SNAPSHOT PROVENANCE:
PROVEN

LIVE PHASE 2 PROVENANCE:
PROVEN

ALIAS KEY PRESERVATION:
PROVEN

READER NORMALIZATION:
PROVEN

AUTHORITATIVE FIELD OWNERSHIP:
PROVEN

CURRENT AUTHORITY MISMATCH:
NONE OBSERVED AFTER THIS CHANGE

CANONICAL ROW AUTHORITY:
- `pipeline_source`: `CANONICAL_RANKED_SNAPSHOT`
- `status_authority`: `CANONICAL_CANDIDATE_POOL`
- `rank_authority`: `CANONICAL_RANKING`
- `execution_eligibility`: `False`
- `execution_eligibility_authority`: `CANONICAL_RANKED_SNAPSHOT`
- `phase2_status`: derived from rank bucket or score-eligibility state
- `phase2_score` / `raw_strategy_score`: derived from the rank record's `final_score`
- `fallback_state`: explicitly `none` for the canonical test fixture

LIVE EXECUTABLE ROW AUTHORITY:
PROVEN
- `pipeline_source`: `LIVE_PHASE2`
- `status_authority`: `LIVE_PHASE2_SELECTION` in the selection-only path used by the test
- `rank_authority`: `LIVE_PHASE2_RANKING`
- `execution_eligibility`: `True`
- `execution_eligibility_authority`: `LIVE_PHASE2_SELECTION`
- `blocked_reason` / `advisory_reason`: derived from the row reason fields, not synthesized

LIVE ADVISORY ROW AUTHORITY:
PROVEN
- `pipeline_source`: `LIVE_PHASE2`
- `status_authority`: `LIVE_PHASE2_SELECTION`
- `rank_authority`: `LIVE_PHASE2_RANKING`
- `execution_eligibility`: `False`
- `execution_eligibility_authority`: `LIVE_PHASE2_SELECTION`
- `advisory_reason`: derived from the advisory row reason field

LIVE BLOCKED ROW AUTHORITY:
PROVEN
- `pipeline_source`: `LIVE_PHASE2`
- `status_authority`: `LIVE_PHASE2_TRUTH`
- `rank_authority`: `LIVE_PHASE2_RANKING`
- `execution_eligibility`: `False`
- `execution_eligibility_authority`: `LIVE_PHASE2`
- `blocked_reason`: derived from the blocked row blocker/reason fields

ROW CLASS COVERAGE:
PROVEN
- canonical ranked snapshot executable row
- live Phase 2 executable row
- live Phase 2 advisory row
- live Phase 2 blocked row

EVIDENCE HIERARCHY RESULT:
PROVEN
The authority fields are now sourced from the row producer that owns them. The canonical ranked snapshot owns only canonical ranking provenance, while live Phase 2 owns live truth and selection provenance. The dashboard reader remains a reader and does not invent authority.

CANONICAL SNAPSHOT PRODUCER:
PROVEN
`core/canonical_ranked_ui_adapter.py` now wraps ranked rows with explicit canonical provenance, and `core/runtime_snapshot_producer.py` continues to preserve alias keys when writing the canonical ranked snapshot payload.

LIVE PHASE 2 PRODUCER:
PROVEN
`core/orchestrator.py` now stamps the live payload after Phase 2 normalization so that live rows carry a source authority, a ranking authority, and execution eligibility provenance.

TOP-OPPORTUNITY READ PATH:
PROVEN
`dashboard/readers/snapshot_reader.py` still normalizes top-opportunity payloads through `normalize_top_opportunity_payload(...)` and preserves the canonical alias keys.

STATUS OWNERSHIP:
PROVEN
Canonical ranked rows do not claim execution truth. Live rows claim the execution-status authority that belongs to the live Phase 2 path.

SCORE OWNERSHIP:
PROVEN
Canonical ranked rows carry the rank score provenance from the canonical snapshot. Live rows carry the live Phase 2 score provenance through the annotated row fields, not through a second scoring pipeline.

RANK OWNERSHIP:
PROVEN
Rank authority stays on the ranking pipeline, with live rows marked `LIVE_PHASE2_RANKING` and canonical rows marked `CANONICAL_RANKING`.

EXECUTION-ELIGIBILITY OWNERSHIP:
PROVEN
Execution eligibility is explicitly false on canonical ranked rows and is explicitly stamped on live Phase 2 rows rather than implied by legacy status fields.

FALLBACK SEMANTICS:
PROVEN
Fallback state is derived from row evidence, not invented. The canonical ranked snapshot test proves the non-fallback state remains `none`.

CANONICAL RANKED SNAPSHOT TEST:
PROVEN
`tests/test_ranked_pipeline_runtime_evidence_wiring.py` now asserts the canonical alias keys plus the canonical authority fields on the top executable row.

LIVE EXECUTABLE TEST:
PROVEN
`tests/test_runtime_execution_truth_evidence.py` now asserts the live Phase 2 authority fields on the top executable row.

LIVE ADVISORY TEST:
PROVEN
`tests/test_runtime_execution_truth_evidence.py` now asserts the live Phase 2 authority fields on the top advisory row.

LIVE BLOCKED TEST:
PROVEN
`tests/test_runtime_execution_truth_evidence.py` now asserts the live Phase 2 authority fields on the top blocked row.

FOCUSED TEST RESULT:
70 passed, 22 warnings

FOCUSED COMMAND:
`python -m pytest -q tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_runtime_execution_truth_evidence.py tests/test_dashboard_canonical_ranked_source.py tests/test_edge58_top_opportunity_executable_truth.py tests/test_edge59_top_opportunity_truth_reader_wiring.py tests/test_dashboard_live_suggestions.py`

STATIC CHECKS:
PASS_FOR_MODIFIED_FILES

The modified Python files passed `python -m py_compile`, `ruff check`, and `git diff --check`. An earlier broader ruff invocation against `core/orchestrator.py` surfaced existing repository-wide lint noise in that file, but the files changed for this task are clean.

FULL SUITE:
1 failed, 6037 passed, 24 deselected, 934 warnings in 762.31s

FIRST FAILURE:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

The failure remains the known unrelated auth baseline:
`RuntimeError: [AUTH] missing_kite_access_token`

RISKS:
- The repository-wide suite still has the known unrelated auth failure.
- The new authority fields are proven by focused tests, but the repository-wide suite is not green because of the baseline auth issue.
- The live authority path still depends on the shape of the upstream Phase 2 classification payload; this audit does not change that contract.

ROLLBACK:
Revert the authority-annotation changes in `core/top_opportunity_executable_truth.py`, `core/canonical_ranked_ui_adapter.py`, and `core/orchestrator.py`, then remove the added provenance assertions from the two tests.

EXPLICIT NON-CLAIMS:
- No strategy formulas changed.
- No ranking formulas changed.
- No Phase 2 decision logic changed.
- No broker, order, execution, or feed behavior changed.
- No live-readiness, profitability, or production-certification claim is made.
- No new dashboard route was introduced.
