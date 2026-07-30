# Testing directory

This directory contains the structured QA requirements catalog, the enterprise test plan, and exploratory charters. It does **not** contain generated passing tests.

## Files

- `testing/TEST_CASES.csv` — 315 structured behavioral requirements/candidate cases.
- `testing/TEST_PLAN.md` — test plan and scope.
- `testing/CHARTERS.md` — exploratory and ad-hoc charters.
- `testing/generate_test_cases.py` — regenerates the structured catalog.
- `testing/generate_pytest_skeletons.py` — renders catalog rows as non-executable Markdown backlog under `testing/generated_case_backlog/`.

## Regenerate the catalog

```bash
python testing/generate_test_cases.py
```

## Render the backlog

```bash
python testing/generate_pytest_skeletons.py
```

The historical script name is retained for compatibility, but it must never create `test_*.py`, skipped placeholders, or unconditional assertions. A catalog row becomes automated evidence only after a real test is implemented under `tests/` with fixtures, meaningful assertions, and requirement traceability.

## Run automated tests

```bash
pytest -q tests
```

The executable suite is scoped for NIFTY, BANKNIFTY, and SENSEX with manual approval safety boundaries. Some deterministic harnesses use monkeypatching to run one orchestrator cycle, but monkeypatches must replace external dependencies—not alter the behavior being certified.
