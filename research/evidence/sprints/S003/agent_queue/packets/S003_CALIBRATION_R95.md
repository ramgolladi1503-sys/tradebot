# S003 Board Bootstrap — Native Calibration Executor R95

This is a non-certifying exact-head native execution job. Do not review or repair the candidate.

Exact candidate:
`e89dc2edbedb0544b431aa36f5cfd0e03c2d57e7`

Run from the detached candidate worktree:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board.py --candidate-head e89dc2edbedb0544b431aa36f5cfd0e03c2d57e7`
4. capture the complete stdout and the exact process exit code.

Return a Markdown artifact containing:

- CANDIDATE_HEAD
- PYTHON_VERSION
- COMMAND
- complete STDOUT
- EXIT_CODE
- `RUNTIME_AUTHORITY=NONE`
- `BROKER_ACTIONS=NONE`
- `CALIBRATION_EXECUTION_RESULT=PASS|FAIL`

PASS is allowed only if the observed HEAD exactly matches the candidate, the calibration reports all 32 declared cases executed with zero failures, denominator conservation true, all predeclared metrics at their required values, terminal marker `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, and exit code 0.
