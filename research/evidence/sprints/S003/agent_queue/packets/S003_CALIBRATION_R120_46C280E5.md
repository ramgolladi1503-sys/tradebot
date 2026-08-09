# S003 autonomous exact-head Board calibration R120

Exact candidate: `46c280e562daf81fd53d355c7ceaa3b96f6a9744`

Non-certifying deterministic native execution. Do not repair or review. This packet is executed by the bridge's fixed allowlisted native calibration path, not by the read-only model sandbox.

Required command semantics:
1. `git rev-parse HEAD`
2. `python3 --version`
3. `python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head 46c280e562daf81fd53d355c7ceaa3b96f6a9744`
4. `python3 -m pytest -q tests/mros/test_s003_r011_native_authorization_regressions.py`

Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, COMMANDS, COMPLETE STDOUT, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, CALIBRATION_EXECUTION_RESULT=PASS|FAIL. PASS requires exact HEAD, every declared calibration case executed, zero failures, denominator conservation, all declared metrics satisfied, terminal `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`, the focused R011 provenance regressions passing, and exit 0.
