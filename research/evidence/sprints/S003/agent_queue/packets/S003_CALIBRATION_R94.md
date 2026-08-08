# S003 Board Bootstrap — Native Calibration Executor R94

This is a non-certifying exact-head native execution job. Do not review or repair the candidate.

Exact candidate:
`fdb053a5094154e9e282b5fe076b9b6dc0c12821`

Run from the detached candidate worktree:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head fdb053a5094154e9e282b5fe076b9b6dc0c12821`
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

PASS is allowed only if the observed HEAD exactly matches the candidate, all 39 declared calibration cases execute with zero failures, denominator conservation is true, all predeclared metrics meet their required values, terminal marker `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS` is present, and exit code is 0.
