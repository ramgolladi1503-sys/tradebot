# S003 Autonomous stderr-safe cycle deployment self-test R100

Exact bridge candidate: `499f9ef3f45661f8c59ec03c8b7f09e03a90d9ff`

This is a non-certifying bridge deployment self-test. Do not repair or modify repository state.

Verify on the exact candidate:

1. `mros_autonomous_supervisor.py` imports successfully.
2. `mros_autonomous_cycle_v2.py` imports successfully.
3. The supervisor's `run_s003` routes to `mros_autonomous_cycle_v2.py`.
4. The v2 cycle wrapper captures stdout and stderr separately.
5. A simulated clean `git status --porcelain` with a benign stderr warning does not become dirty stdout.
6. Runtime authority remains NONE and broker actions remain NONE.

Return Markdown containing CANDIDATE_HEAD, PYTHON_VERSION, checks performed, PASS/FAIL for each assertion, EXIT_CODE, RUNTIME_AUTHORITY=NONE, BROKER_ACTIONS=NONE, and terminal `AUTONOMY_STDERR_SAFE_SELFTEST=PASS|FAIL`.
