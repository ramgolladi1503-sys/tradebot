CANDIDATE_HEAD: `b77638c4ae3d3d929dbe3798479b54f4e19d2c60`

PYTHON_VERSION: `Python 3.12.2`

COMMAND:

```bash
git rev-parse HEAD
python3 --version
mkdir -p .mros_tmp && TMPDIR="$PWD/.mros_tmp" python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head b77638c4ae3d3d929dbe3798479b54f4e19d2c60
```

COMPLETE STDOUT:

```text
b77638c4ae3d3d929dbe3798479b54f4e19d2c60
Python 3.12.2
mkdir: .mros_tmp: Operation not permitted
```

EXIT_CODE: `1`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

CALIBRATION_EXECUTION_RESULT=FAIL