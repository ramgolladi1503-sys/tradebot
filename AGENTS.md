# AGENTS.md

## Scope
This file defines guardrails for analytics-focused changes in this repository.

## Non-Negotiable Rules
1. Never change live execution logic in analytics tasks.
2. Keep diffs scoped to the requested analytics objective; do not refactor unrelated modules.
3. Always add or extend tests for any analytics behavior change.
4. Run `pytest` for all newly added/updated tests before finishing.

## Safety and Change Discipline
1. Treat analytics code as production-impacting: fail closed on invalid inputs.
2. Preserve backward compatibility for existing analytics outputs unless explicitly approved.
3. Prefer deterministic logic and explicit schema validation for logs/reports.
4. Use atomic file writes for report artifacts whenever practical.
5. Do not touch secrets, auth flows, broker sessions, or order routing in analytics work.

## Test Execution Requirement
For every analytics change:
1. Run targeted tests first, e.g. `pytest -q tests/test_<area>.py`.
2. If multiple analytics modules are touched, run all relevant test files.
3. Include test results in the final handoff summary.

## How to Run Daily Intelligence Report
```bash
# Daily trade report artifacts (JSON + CSV)
python scripts/daily_report.py

# Daily scorecard summary
python scripts/daily_scorecard.py

# Optional: daily audit report
python scripts/run_daily_audit.py
```

