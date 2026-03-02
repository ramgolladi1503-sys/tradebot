# AGENTS.md

## Analytics Guardrails
1. Analytics code must never change live execution logic.
2. All analytics workflows must run offline and use `core.analytics.store` + `core.analytics.outcome_replay`.
3. Every new analytics module requires tests.
4. Always run `pytest -q` for analytics tests after changes.

## Daily Intelligence Report
```bash
# Default: yesterday (local timezone)
scripts/run_daily_intel.sh

# Explicit date
scripts/run_daily_intel.sh --date YYYY-MM-DD
```
