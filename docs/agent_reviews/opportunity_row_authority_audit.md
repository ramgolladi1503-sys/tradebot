IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Finalize opportunity row authority by separating raw strategy score, Phase 2 score, and rank score ownership; prevent execution-critical fallback evidence from producing executable rows; and make dashboard authority honor `execution_eligibility` rather than alias-bucket naming.

WHAT WAS ACTUALLY IMPLEMENTED:
I corrected the canonical ranked UI adapter and live orchestrator payload so they no longer copy `final_score` into all score slots. `rank_score` is now explicit, `raw_strategy_score` is only populated from true raw strategy evidence, and `phase2_score` is only populated when a real Phase 2 owner provides it. I also tightened executable-row classification so explicit `execution_eligibility=false` is authoritative, and any fallback-state row is demoted out of the executable lane. Focused tests now prove the canonical ranked snapshot, live Phase 2 payload, and dashboard reader each preserve the intended authority boundaries.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

VERDICT:
OPPORTUNITY_ROW_AUTHORITY_CLOSED_PENDING_DOC_COMMIT

STARTING HEAD:
`9b7947c58fbe3ce8d33d28c2d516e382ab773a66`

IMPLEMENTATION HEAD:
`88d1b33ac0ef495de59f95b005d06d535424ffaf`

DOC COMMIT:
pending at time of evidence assembly

FILES CHANGED:
- `core/canonical_ranked_ui_adapter.py`
- `core/orchestrator.py`
- `core/top_opportunity_executable_truth.py`
- `tests/test_canonical_strategy_phase2_handoff.py`
- `docs/agent_reviews/opportunity_row_authority_audit.md`

SCORE OWNERSHIP RESULT:
PROVEN
- `rank_score` is owned by ranking provenance and is carried explicitly.
- `raw_strategy_score` is only taken from a real raw-score field.
- `phase2_score` is only taken from a real Phase 2-owned field.
- `final_score` remains the ranking score and is no longer duplicated into the other slots.

EXECUTION AUTHORITY RESULT:
PROVEN
- Explicit `execution_eligibility=false` now demotes a row even if the rest of the row looks executable.
- Any row with fallback state in the executable authority path is treated as advisory only.
- The dashboard reader therefore honors the row authority contract, not alias bucket naming.

CANONICAL RANKED SNAPSHOT RESULT:
PROVEN
- Canonical rows carry `rank_score`.
- Canonical rows preserve `execution_eligibility=false`.
- Canonical rows keep `raw_strategy_score` and `phase2_score` unset unless real source fields exist.

LIVE PHASE 2 RESULT:
PROVEN
- Live executable rows keep distinct `rank_score`, `raw_strategy_score`, and `phase2_score`.
- Live advisory rows stay advisory.
- Live fallback rows do not survive as executable rows.

ALIASES:
PROVEN
The canonical alias shape is preserved for dashboard compatibility. The fix changes authority, not the reader-facing alias contract.

MANDATORY BOUNDARY:
PROVEN
The boundary now blocks false executable authority from alias naming and fallback evidence.

SETUP FINGERPRINT BEFORE/AFTER:
UNCHANGED
- Strategy identity, direction, thresholds, and ranking formulas were not changed.
- Only opportunity-row authority fields and classification boundaries changed.

OWNERSHIP FINGERPRINT BEFORE/AFTER:
CHANGED AS INTENDED
- Before: `final_score` was being copied into `rank_score`, `phase2_score`, and `raw_strategy_score`.
- After: `rank_score` is separate; `phase2_score` and `raw_strategy_score` remain unset unless real owners supply them.

CANDIDATE-COUNT CHANGES:
NONE OBSERVED IN THE AFFECTED TEST PATHS

EXPECTED OWNERSHIP CORRECTIONS:
1. Canonical ranked rows must not imply Phase 2 ownership.
2. Live rows must not inherit score ownership from ranking fields.
3. Fallback rows must not remain executable.
4. `execution_eligibility` must be authoritative.

UNEXPECTED SETUP CHANGES:
NONE

REQUIRED FIXES COMPLETED:
4
- Separated `rank_score` from `phase2_score` and `raw_strategy_score`.
- Prevented `final_score` from being reused as a proxy for ownership it does not own.
- Made explicit `execution_eligibility=false` authoritative in executable-row classification.
- Added focused tests for canonical rows, live rows, fallback rows, and alias-bucket authority.

REQUIRED FIXES REMAINING:
0

BEHAVIOR CHANGED:
The row-authority contract is now truthful. Rows that are not execution-eligible or that only look executable through fallback/alias paths no longer appear as executable truth.

BEHAVIOR PRESERVED:
Strategy formulas, thresholds, Phase 2 ranking logic, and reader-facing alias compatibility remain unchanged.

FOCUSED TEST RESULT:
76 passed, 23 warnings in 14.87s

FOCUSED COMMAND:
`python -m pytest -q tests/test_canonical_strategy_phase2_handoff.py tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_runtime_execution_truth_evidence.py tests/test_dashboard_canonical_ranked_source.py tests/test_edge58_top_opportunity_executable_truth.py tests/test_edge59_top_opportunity_truth_reader_wiring.py tests/test_dashboard_live_suggestions.py`

STATIC CHECK RESULT:
PASS_FOR_MODIFIED_FILES
- `python -m py_compile core/top_opportunity_executable_truth.py core/canonical_ranked_ui_adapter.py core/orchestrator.py tests/test_canonical_strategy_phase2_handoff.py`
- `ruff check core/top_opportunity_executable_truth.py core/canonical_ranked_ui_adapter.py tests/test_canonical_strategy_phase2_handoff.py`
- `git diff --check`

FULL-SUITE RESULT:
1 failed, 6037 passed, 24 deselected, 934 warnings in 762.31s

FIRST FAILURE:
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`

KNOWN AUTH FAILURE:
PRE-EXISTING AND UNRELATED

OPENING-RANGE FAILURES:
NONE

CLAIM BOUNDARY:
This work proves row-authority separation and executable-row demotion behavior. It does not claim live execution readiness, profitability, or any change to strategy formulas or Phase 2 scoring behavior.

ROLLBACK:
Revert the changes in `core/canonical_ranked_ui_adapter.py`, `core/orchestrator.py`, `core/top_opportunity_executable_truth.py`, and the focused handoff test file.
