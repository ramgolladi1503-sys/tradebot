# PR #936 remote CI result — 2026-09-27

- PR: https://github.com/ramgolladi1503-sys/tradebot/pull/936
- Tested commit: `043577edd4b2c79c763690a64bbc6cfdf1cb7a0f`
- Workflow: `ci`, run `36310696255`, unit_tests job `108595911935`
- Result: **FAILURE** at `Run fast deterministic tests`; health gate skipped as dependent work.
- `Checkout`, disk cleanup, Python setup, and dependency installation succeeded.
- Collection failed in the five gateway test modules because the workflow's `requirements.txt` install does not install Pydantic. Exact error: `ModuleNotFoundError: No module named 'pydantic'`.
- The workflow also does not install Pandera. Gateway tests were not executed by this run.
- No CI files or root dependency manifests were changed: the task's governing repository instructions classify them as protected. Do not mark tests skipped or remove assertions to turn this check green.
- Required dependency/CI integration remains a separate authorized change. The local isolated environment ran gateway tests successfully (see `ACCEPTANCE_TEST_LOG_20260927.txt`); that does not substitute for this failed CI run.
