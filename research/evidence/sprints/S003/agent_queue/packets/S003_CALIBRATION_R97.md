# MROS S003 DETERMINISTIC BOARD CALIBRATION — NATIVE RETRY

You are non-certifying calibration executor `R97`. Do not review or repair the candidate.

Exact candidate: `c1a4ab07daf19db636c6ea8b0d951c642808d32e`.

1. Verify `git rev-parse HEAD` equals the exact candidate.
2. Verify `git status --porcelain` is empty before execution.
3. Create/use a private temporary directory under `$HOME/.codex/tmp` (not the candidate worktree), export `TMPDIR` to that directory, and run exactly:
   `python3 scripts/mros/calibrate_review_audit_board.py`
4. Capture `python3 --version`, complete stdout/stderr, and exit code.
5. Verify `git status --porcelain` remains empty after execution.
6. Remove only the private temporary directory you created.
7. Do not alter repository files, runtime/broker behavior, or authority.

Return Markdown containing: CANDIDATE_HEAD, PYTHON_VERSION, COMMAND, PRE_STATUS, STDOUT, EXIT_CODE, POST_STATUS, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, and `CALIBRATION_EXECUTION_RESULT=PASS|FAIL`. PASS requires exact HEAD, clean pre/post status, calibration exit 0, and the stdout final marker `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`.