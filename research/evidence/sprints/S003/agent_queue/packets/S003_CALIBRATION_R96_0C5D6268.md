# S003 Board Bootstrap — Native Calibration Executor R96

Non-certifying exact-head native execution only. Do not review or repair.

Exact candidate: `0c5d6268ef224450cd881da588efcce04c630414`

Run from the detached candidate worktree:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head 0c5d6268ef224450cd881da588efcce04c630414`
4. Capture complete stdout and exact exit code.

Return CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, complete STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL.

PASS only if exact HEAD matches, all 41 declared cases execute, zero fail, denominator conservation is true, all declared metrics meet target, terminal marker S003_BOARD_DETERMINISTIC_CALIBRATION_PASS appears, and exit code is 0.
