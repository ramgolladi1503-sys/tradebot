# S003 Board Bootstrap — Native Calibration Executor R93

This is a non-certifying exact-head native execution job. Do not review or repair the candidate.

Exact candidate:
`d6b502d55f6d0a2b66719607b816873d9bf78d62`

Run from the detached candidate worktree:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head d6b502d55f6d0a2b66719607b816873d9bf78d62`
4. capture the complete stdout and exact process exit code.

Return a Markdown artifact containing:
- CANDIDATE_HEAD
- PYTHON_VERSION
- COMMAND
- complete STDOUT
- EXIT_CODE
- RUNTIME_AUTHORITY=NONE
- BROKER_ACTIONS=NONE
- CALIBRATION_EXECUTION_RESULT=PASS|FAIL

PASS is allowed only if observed HEAD exactly matches the candidate, all 39 declared cases execute, zero cases fail, denominator conservation is true, all calibration metrics meet their declared targets, terminal marker `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS` appears, and exit code is 0.
