# MROS S003 — Autonomous Bridge Exact-Head Self-Test R98

CANDIDATE_HEAD: `fce4039005a2c8d9eba15751e399f8e516f66d85`

PYTHON_VERSION: `Python 3.12.2`

TEST_COMMAND:

```bash
python3 -m pytest -q tests/mros/test_mros_agent_bridge.py tests/mros/test_mros_autonomous_supervisor.py tests/mros/test_mros_state_transition_engine.py
```

Complete pytest output:

```text
Traceback (most recent call last):
...
FileNotFoundError: [Errno 2] No usable temporary directory found in ['/var/folders/7h/d5fnr_sn43q_cxnd8vk1m2vm0000gn/T/', '/tmp', '/var/tmp', '/usr/tmp', '/Users/madhuram/.mros-agent-bridge/jobs/mros-reviewer-R98-2f6421b0']
```

Pytest exit code: `1`

PY_COMPILE_RESULT: FAIL

```text
[Errno 1] Operation not permitted: 'scripts/mros/__pycache__'
```

Py_compile exit code: `1`

EXIT_CODE: `1`

RUNTIME_AUTHORITY=NONE

BROKER_ACTIONS=NONE

AUTONOMY_BRIDGE_SELFTEST=FAIL