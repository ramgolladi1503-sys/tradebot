**Testing Directory**
This directory contains a structured test catalog, a generator, and manual charters.

**Files**
`testing/TEST_CASES.csv` 315 structured test cases
`testing/TEST_PLAN.md` test plan and scope
`testing/CHARTERS.md` adhoc charters
`testing/generate_test_cases.py` generator
`testing/generate_pytest_skeletons.py` pytest skeleton generator

**Regenerate Cases**
`python testing/generate_test_cases.py`

**Generate Pytest Skeletons**
`python testing/generate_pytest_skeletons.py`

**Run Unit Tests**
`pytest -q tests`

**Notes**
These tests are scoped for NIFTY, BANKNIFTY, and SENSEX with manual approval only.

**Test Harness (No Production Code Changes)**
These tests use monkeypatching to run one orchestrator cycle without modifying `core/orchestrator.py`.

Run:
`pytest -q testing/tests`

**Notes**
Generated skeletons are skipped by default; fill in assertions to activate them.
