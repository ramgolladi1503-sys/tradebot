# Agent Work Contract: PR 639 - Structural Audits for Opening Drive and Mean Reversion

## 1. Scope Guard
**Allowed Paths:** `tests/test_mean_reversion_vertical_slice.py`, `tests/test_orchestrator_depth_ws_startup.py`
**Forbidden Paths:** Any `core/` files, live execution logic, etc.
**Goal:** Implement structural audits for Opening Drive and Mean Reversion and fix related CI failures.

## 2. Grill Me
Risk is extremely low as this only adds and modifies test code in `tests/`. No live execution paths are modified.

## 3. Hermes
The design strictly follows the testing patterns established in the repository. We use standard pytest assertions to prove the behavior of structural audits for mean reversion.

## 4. GSD
- Fixed `tests/test_orchestrator_depth_ws_startup.py` failure.
- Resolved merge conflicts by cleanly incorporating `origin/main`'s versions.

## 5. QA/Safety
- All tests pass locally using `pytest`.
- No `core/` files were mutated.
- The `RuntimeError("boom")` in `test_start_depth_ws_or_raise_fail_closed` is now correctly raised by mocking credentials checking.

## 6. Acceptance Proof
Pytest results show 100% pass rate on the touched test files.

## 7. Runtime Proof Required After Merge
None. This is test-only.

## 8. What This PR Does Not Prove
This PR does not prove profitability or runtime safety of the strategies themselves. It only proves structural consistency of the candidates.

## 9. Human Approval
Explicitly requested by user.
