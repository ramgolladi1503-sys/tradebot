CANDIDATE_HEAD: `e89dc2edbedb0544b431aa36f5cfd0e03c2d57e7`

PYTHON_VERSION: `Python 3.12.2`

COMMAND: `python3 scripts/mros/calibrate_review_audit_board.py --candidate-head e89dc2edbedb0544b431aa36f5cfd0e03c2d57e7`

STDOUT:
```text
PASS | CAL-001 | expected=ACCEPT observed=ACCEPT
PASS | CAL-002 | expected=REJECT observed=REJECT
PASS | CAL-003 | expected=REJECT observed=REJECT
PASS | CAL-004 | expected=REJECT observed=REJECT
PASS | CAL-005 | expected=ACCEPT observed=ACCEPT
PASS | CAL-006 | expected=REJECT observed=REJECT
PASS | CAL-007 | expected=REJECT observed=REJECT
PASS | CAL-008 | expected=REJECT observed=REJECT
PASS | CAL-009 | expected=ACCEPT observed=ACCEPT
PASS | CAL-010 | expected=REJECT observed=REJECT
PASS | CAL-011 | expected=REJECT observed=REJECT
PASS | CAL-012 | expected=REJECT observed=REJECT
PASS | CAL-013 | expected=REJECT observed=REJECT
PASS | CAL-014 | expected=REJECT observed=REJECT
PASS | CAL-015 | expected=REJECT observed=REJECT
PASS | CAL-016 | expected=REJECT observed=REJECT
PASS | CAL-017 | expected=ACCEPT observed=ACCEPT
PASS | CAL-018 | expected=REJECT observed=REJECT
PASS | CAL-019 | expected=REJECT observed=REJECT
PASS | CAL-020 | expected=REJECT observed=REJECT
PASS | CAL-021 | expected=REJECT observed=REJECT
PASS | CAL-022 | expected=REJECT observed=REJECT
PASS | CAL-023 | expected=REJECT observed=REJECT
PASS | CAL-024 | expected=REJECT observed=REJECT
PASS | CAL-025 | expected=REJECT observed=REJECT
PASS | CAL-026 | expected=REJECT observed=REJECT
PASS | CAL-027 | expected=REJECT observed=REJECT
PASS | CAL-028 | expected=REJECT observed=REJECT
PASS | CAL-029 | expected=REJECT observed=REJECT
PASS | CAL-030 | expected=REJECT observed=REJECT
PASS | CAL-031 | expected=REJECT observed=REJECT
PASS | CAL-032 | expected=ACCEPT observed=ACCEPT
METRICS | {"declared_cases": 32, "executed_cases": 32, "extra_cases": [], "false_acceptance_rate": 0.0, "false_rejection_rate": 0.0, "known_bad_detection_rate": 1.0, "known_good_acceptance_rate": 1.0, "missing_cases": []}
SUMMARY | cases=32 pass=32 fail=0 denominator_conserved=true
S003_BOARD_DETERMINISTIC_CALIBRATION_PASS
```

EXIT_CODE: `0`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=PASS