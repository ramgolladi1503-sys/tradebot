CANDIDATE_HEAD: `c1a4ab07daf19db636c6ea8b0d951c642808d32e`

PYTHON_VERSION: Not captured; private `TMPDIR` creation failed.

COMMAND: `python3 scripts/mros/calibrate_review_audit_board.py`

PRE_STATUS:
```text
warning: Empty last update token.
```

STDOUT:
```text

```

EXIT_CODE: `125` (calibration not executed)

POST_STATUS:
```text
warning: Empty last update token.
```

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=FAIL

Reason: creating the required private temporary directory under `$HOME/.codex/tmp` failed with `Operation not permitted`. The status command also emitted a warning, so clean repository status was not proven.