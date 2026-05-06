# Test Reports — Tradebot

## Current CI gate

The repository includes a GitHub Actions workflow:

```text
.github/workflows/portfolio-ci.yml
```

This workflow validates the project as a recruiter-facing fintech QA/SDET portfolio.

## What the CI checks today

- README exists.
- Architecture SVG exists.
- Fintech QA one-pager exists.
- README includes problem statement, architecture, test strategy, failure modes, and roadmap.
- A Markdown CI report artifact is generated on each run.

## Why this matters

Tradebot contains broker/runtime-oriented workflows that may require secrets, market sessions, or stable local dependencies. The current CI gate avoids fake confidence and validates the portfolio assets first.

## Next test-report upgrades

- Safe pytest subset report.
- Offline health gate report.
- Contract resolver regression report.
- Data freshness simulation report.
- Risk gate regression report.
- Reconciliation report.
- Dashboard schema contract report.
