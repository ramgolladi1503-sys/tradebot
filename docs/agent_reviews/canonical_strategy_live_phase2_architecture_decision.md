IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Decide whether canonical ranked strategy candidates should be integrated into live Phase 2, using evidence-only review of the existing runtime and test boundary.

WHAT WAS ACTUALLY IMPLEMENTED:
I performed an audit-only architecture review of the canonical ranked snapshot path, the live Phase 2 path, and the top-opportunity truth reader. No production code was changed. The evidence shows that canonical ranked candidates already live on a read-only snapshot path, while live Phase 2 keeps its own execution authority and selection semantics. The correct decision is to keep canonical ranked snapshots and live Phase 2 separate rather than wiring canonical candidates directly into live Phase 2.

ARCHITECTURE CHANGE:
NONE

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

STARTING HEAD:
`2c5ef44bb50e2572193b93f0ff6a7dc80f84cf6b`

WORKTREE:
`/Users/madhuram/tradebot-canonical-strategy-phase2-handoff`

BRANCH:
`fix/canonical-strategy-phase2-handoff`

CURRENT HEAD:
`2c5ef44bb50e2572193b93f0ff6a7dc80f84cf6b`

SUBAGENT STATUS:
Requested review lanes could not be spawned in this session because the agent thread limit was reached (`collab spawn failed: agent thread limit reached`).

ARCHITECTURE DECISION:
KEEP_CANONICAL_AND_LIVE_PHASE2_SEPARATE

WHY INTEGRATION WAS REJECTED:
- `core/runtime_snapshot_producer._build_and_write_canonical_ranked_snapshot()` calls `build_ranked_opportunity_report(...)` and writes `ranked_pipeline_latest.json`; it does not route those rows into `run_engine_phase2(...)`. See `core/runtime_snapshot_producer.py:409-415` and `core/runtime_snapshot_producer.py:427-460`.
- `core/ranking_orchestrator.build_ranked_opportunity_report(...)` is explicitly documented as read-only and says it does not promote candidates, mutate scores, or wire results into runtime action paths. See `core/ranking_orchestrator.py:163-168`.
- `core/canonical_ranked_ui_adapter.adapt_candidate_rank_record_to_ui(...)` stamps canonical rows with `pipeline_source=CANONICAL_RANKED_SNAPSHOT`, `status_authority=CANONICAL_CANDIDATE_POOL`, `rank_authority=CANONICAL_RANKING`, and `execution_eligibility=False`. See `core/canonical_ranked_ui_adapter.py:40-46`.
- `core/orchestrator._build_top_opportunities_payload(...)` derives live top-opportunity rows from `run_engine_phase2(...)`, not from the canonical ranked snapshot path. It stamps live rows with `pipeline_source=LIVE_PHASE2` and live-specific authorities. See `core/orchestrator.py:1230-1370`.
- `core/top_opportunity_executable_truth.classify_top_opportunity_row(...)` and `_truth_reason(...)` keep the top-opportunity reader fail-closed on fallback or non-eligible rows, which is reader truth, not a bridge from canonical ranking to live execution. See `core/top_opportunity_executable_truth.py:244-315`.
- The dashboard snapshot reader test proves the dashboard reads the canonical ranked path only and does not fall back to the legacy live top-opportunities path. See `tests/test_dashboard_canonical_ranked_source.py:15-54`.

WHY A PARTIAL BRIDGE WAS NOT CHOSEN:
- A partial bridge would duplicate ownership semantics without a new contract boundary.
- Canonical ranked rows are already intentionally non-executable by authority.
- Live Phase 2 already has its own execution truth, blockers, and fallback handling.
- The cleanest safe decision is to keep the two products separate and preserve the existing reader-normalization boundary.

EVIDENCE MATRIX:
| Path | Role | Authority | Result |
| --- | --- | --- | --- |
| `core.runtime_snapshot_producer -> build_ranked_opportunity_report` | canonical ranked snapshot writer | canonical audit authority | read-only snapshot only |
| `core.ranking_orchestrator.build_ranked_opportunity_report` | canonical candidate ranking | read-only ranking authority | no runtime action wiring |
| `core.canonical_ranked_ui_adapter` | canonical UI projection | canonical snapshot authority | `execution_eligibility=False` |
| `core.orchestrator._build_top_opportunities_payload` | live top-opportunity writer | live Phase 2 authority | uses `run_engine_phase2(...)` |
| `core.top_opportunity_executable_truth` | reader normalization | read-only truth contract | demotes fallback / non-eligible rows |

EXACT TEST PROOF:
- Focused authority slice: `105 passed, 23 warnings in 14.71s`
- Commands run:
  - `python -m pytest -q tests/test_canonical_strategy_phase2_handoff.py tests/test_ranked_pipeline_runtime_evidence_wiring.py tests/test_runtime_execution_truth_evidence.py tests/test_dashboard_canonical_ranked_source.py tests/test_edge58_top_opportunity_executable_truth.py tests/test_edge59_top_opportunity_truth_reader_wiring.py tests/test_dashboard_live_suggestions.py tests/test_candidate_pool.py tests/test_candidate_pool_orchestrator.py tests/test_candidate_pool_contract_snapshots.py`

FULL-SUITE RESULT:
- Prior repository-wide run remains not green because of the known unrelated auth failure:
  - `1 failed, 6055 passed, 24 deselected, 935 warnings in 741.59s`
  - failure: `tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
  - error: `RuntimeError: [AUTH] missing_kite_access_token`

CONCLUSION:
The canonical candidate pipeline should remain separate from live Phase 2. If a future bridge is desired, it must be an explicit, versioned handoff with new ownership semantics, not an implicit reuse of the canonical ranked snapshot as live execution authority.

CLAIM BOUNDARY:
This decision proves architecture separation, read-only canonical ranking, and live Phase 2 authority ownership. It does not prove profitability, production readiness, or live execution readiness.
