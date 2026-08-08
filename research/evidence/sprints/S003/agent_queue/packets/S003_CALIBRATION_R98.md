# MROS S003 — Native Deterministic Board Calibration Executor

Role: `R98` non-certifying calibration executor.

This is NOT a Board certification review and MUST NOT authorize the Review Board, Audit Board, S003, M9, or runtime authority.

Exact candidate SHA:
`c1a4ab07daf19db636c6ea8b0d951c642808d32e`

In the fresh detached read-only worktree:

1. Verify `git rev-parse HEAD` exactly equals the candidate SHA above.
2. Record `python3 --version`.
3. Execute exactly:
   `python3 scripts/mros/calibrate_review_audit_board.py`
4. Record the complete calibration stdout and the command exit code.
5. Do not edit the repository. Do not weaken tests. Do not run runtime/broker/order actions.
6. Return a Markdown evidence artifact with:
   - `CANDIDATE_HEAD`
   - `PYTHON_VERSION`
   - `COMMAND`
   - fenced complete `STDOUT`
   - `EXIT_CODE`
   - `RUNTIME_AUTHORITY=NONE`
   - `BROKER_ACTIONS=NONE`
   - `CALIBRATION_EXECUTION_RESULT=PASS|FAIL`

`CALIBRATION_EXECUTION_RESULT=PASS` is allowed only when exact HEAD matches, the harness ends with `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, and exit code is 0.
