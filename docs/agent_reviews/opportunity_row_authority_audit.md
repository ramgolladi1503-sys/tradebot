IMPLEMENTATION DIRECTION:
RIGHT_WITH_GAPS

APPROVED OBJECTIVE:
Finalize opportunity row authority by proving the runtime distinguishes strategy-input proxy provenance from execution-critical fallback evidence, while preserving score ownership and dashboard alias compatibility.

WHAT WAS ACTUALLY IMPLEMENTED:
I repaired the executable-row classifier so explicit fallback state now fails closed even when legacy executable fields look clean, and I extended the fallback vocabulary so execution-critical markers such as `fallback_ltp`, `fallback_bid`, `fallback_ask`, `fallback_spread`, `estimated_price`, `stale_quote`, `missing_freshness`, `synthetic_liquidity`, and `degraded_quote` are treated as non-executable sources. Strategy-input proxy provenance, including `VWAP_UNIT_WEIGHT_PROXY`, is still not treated as an execution fallback when quote, spread, freshness, and liquidity evidence are authoritative. I added focused tests that prove the proxy/control distinction, explicit fallback-state demotion, unknown fallback fail-closed behavior, and alias-authority demotion.

ARCHITECTURE CHANGE:
NECESSARY_MINIMAL

SCOPE STATUS:
IN_SCOPE

EVIDENCE STATUS:
PROVEN

VERDICT:
OPPORTUNITY_ROW_AUTHORITY_CLOSED_WITH_PREEXISTING_AUTH_FAILURE

STARTING HEAD:
`79e2651fd4cd103ede36207dc82b8964e3615a7e`

IMPLEMENTATION/TEST COMMIT:
`ceab3c4483308b162a6a22870fafacb1b89b7daa`

EVIDENCE COMMIT:
docs-only commit created after the implementation/test commit

FINAL HEAD:
to be filled by the docs-only commit hash in the handback

LOCAL HEAD:
same as FINAL HEAD after the docs-only commit

REMOTE HEAD:
same as FINAL HEAD after push

FILES CHANGED:
- `core/top_opportunity_executable_truth.py`
- `tests/test_canonical_strategy_phase2_handoff.py`
- `docs/agent_reviews/opportunity_row_authority_audit.md`

SUBAGENTS DEPLOYED:
3 background verification threads were created for the requested taxonomy, frozen-control, and semantic-test lanes. Their scopes were isolated and read-only for the audit lanes; the main thread reproduced the decisive behavior locally and used that evidence to make the repair.

FALLBACK TAXONOMY RESULT:
Execution-critical fallback markers are now fail-closed, and strategy-input proxy provenance is not demoted by itself.

STRATEGY INPUT PROXY DEFINITION:
`VWAP_UNIT_WEIGHT_PROXY` is a strategy-input provenance flag. It does not imply fallback execution evidence on its own.

EXECUTION FALLBACK DEFINITION:
Fallback execution evidence includes `recovered_fallback`, `fallback_recovered`, `fallback_ltp`, `fallback_bid`, `fallback_ask`, `fallback_spread`, `estimated_price`, `stale_quote`, `missing_freshness`, `synthetic_liquidity`, and `degraded_quote`. These values fail closed.

UNKNOWN PROVENANCE POLICY:
Unknown fallback provenance fails closed. If the row cannot be classified as authoritative execution evidence, it is not executable.

VWAP_UNIT_WEIGHT_PROXY RESULT:
PASS
The proxy row remained executable when quote, spread, freshness, and liquidity evidence were authoritative.

FALLBACK OPTION PRICE RESULT:
PASS
Explicit fallback-state and fallback price paths demoted the row out of the executable lane.

FALLBACK BID_ASK RESULT:
PASS
Fallback bid/ask markers demoted the row out of the executable lane.

FALLBACK SPREAD RESULT:
PASS
Fallback spread markers demoted the row out of the executable lane.

STALE FRESHNESS RESULT:
PASS
Stale or missing freshness markers demoted the row out of the executable lane.

UNKNOWN FALLBACK RESULT:
PASS
Unknown fallback markers failed closed and did not remain executable.

ALIAS EXECUTION CONTROL RESULT:
PASS
Rows stored under `top_executable_opportunities` are still demoted when they are not execution-eligible or are fallback-classified.

RAW STRATEGY SCORE OWNER:
strategy-owned only

PHASE 2 SCORE OWNER:
Phase-2-owned only

RANK SCORE OWNER:
ranking-owned only

EXECUTION ELIGIBILITY OWNER:
explicit execution authority, not alias naming

OPENING RANGE RETEST CONTROL:
PASS

TREND PULLBACK CONTROL:
PASS

COMPRESSION BREAKOUT CONTROL:
PASS

VWAP RECLAIM CONTROL:
PASS

PRODUCTION DEFECT FOUND:
Reader classification ignored explicit fallback-state authority and also lacked the broader execution-fallback source vocabulary.

PRODUCTION FILES CHANGED:
`core/top_opportunity_executable_truth.py`

TEST FILES CHANGED:
`tests/test_canonical_strategy_phase2_handoff.py`

EVIDENCE FILES CHANGED:
`docs/agent_reviews/opportunity_row_authority_audit.md`

ROLLBACK:
Revert `core/top_opportunity_executable_truth.py` and the added handoff test cases.

FOCUSED TEST TOTALS:
18 passed, 1 warning in 10.01s

FOCUSED COMMAND:
`python -m pytest -q tests/test_canonical_strategy_phase2_handoff.py`

FROZEN CONTROL TOTALS:
57 passed, 1 warning in 11.44s

FROZEN CONTROL COMMAND:
`python -m pytest -q tests/test_opening_range_retest_runtime_owner_enforcement.py tests/test_trend_pullback_temporal_conformance.py tests/test_trend_pullback_temporal_semantics.py tests/test_compression_breakout_range_width_runtime_contract.py tests/test_compression_breakout_phase3b_gap_audit.py tests/test_vwap_reclaim_runtime_source_contract.py tests/test_vwap_reclaim_runtime_conformance.py tests/test_vwap_reclaim_temporal_conformance.py`

STATIC CHECKS:
PASS
`python -m py_compile core/top_opportunity_executable_truth.py tests/test_canonical_strategy_phase2_handoff.py`
`ruff check core/top_opportunity_executable_truth.py tests/test_canonical_strategy_phase2_handoff.py`
`git diff --check`

FULL-SUITE TOTALS:
1 failed, 6055 passed, 24 deselected, 935 warnings in 741.59s

BASELINE FAILURE CLASSIFICATION:
PRE-EXISTING AND UNRELATED
`tests/test_orchestrator_reports_finally.py::test_cycle_exception_still_writes_reports`
`RuntimeError: [AUTH] missing_kite_access_token`

CLAIM BOUNDARY:
This work proves the row-authority distinction and the fail-closed execution-fallback classifier. It does not claim any strategy edge, profitability, live readiness, or Phase 2 handoff completeness.

EXPLICIT NON-CLAIMS:
- No strategy formulas changed.
- No thresholds changed.
- No ranking formulas changed.
- No Phase 2 decision formulas changed.
- No dashboard alias keys changed.
- No broker, order, or execution behavior changed.
- No canonical/live provenance rules changed.
- No historical validation or profitability claim was made.
