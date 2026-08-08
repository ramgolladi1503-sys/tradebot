# S003 autonomous exact-head Board calibration R110

Exact candidate: `b77638c4ae3d3d929dbe3798479b54f4e19d2c60`

Non-certifying native execution. Do not repair or review.

Run:

1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head b77638c4ae3d3d929dbe3798479b54f4e19d2c60`

Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL.

PASS requires exact HEAD, every declared calibration case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, and exit 0.
