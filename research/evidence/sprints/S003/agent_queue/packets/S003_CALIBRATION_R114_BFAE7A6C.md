# S003 autonomous exact-head Board calibration R114

Exact candidate: `bfae7a6cdea9f4af9a39bcbf548b4c944fdeeda5`

Non-certifying deterministic native execution. Do not repair or review. This packet is executed by the bridge's fixed allowlisted native calibration path.

Required command semantics:
1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head bfae7a6cdea9f4af9a39bcbf548b4c944fdeeda5`

Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL. PASS requires exact HEAD, every declared calibration case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, and exit 0.
