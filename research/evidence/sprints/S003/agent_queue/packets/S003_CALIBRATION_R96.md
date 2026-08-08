# MROS S003 BOARD CALIBRATION — R96 NON-CERTIFYING EXECUTOR

This is a deterministic native calibration execution job, not an independent certification review.

Exact candidate SHA:
`5c7c0d6a75e6b8b56362011fb89b66efa29a64b3`

Run only from the detached exact-SHA worktree supplied by the bridge.

Required actions:
1. Record `git rev-parse HEAD` and require exact equality with the candidate SHA.
2. Record `python3 --version`.
3. Run exactly:
   `python3 scripts/mros/calibrate_review_audit_board.py`
4. Capture complete stdout and the true command exit code.
5. Do not modify the repository or any candidate file.
6. Do not create research/runtime authority.

Return a Markdown artifact containing:
- CANDIDATE_HEAD
- PYTHON_VERSION
- COMMAND
- STDOUT
- EXIT_CODE
- RUNTIME_AUTHORITY=NONE
- BROKER_ACTIONS=NONE
- CALIBRATION_EXECUTION_RESULT=PASS|FAIL

PASS is permitted only if the command exits 0 and stdout ends with `S003_BOARD_DETERMINISTIC_CALIBRATION_PASS`.
