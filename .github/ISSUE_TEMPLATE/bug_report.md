---
name: Bug report
about: Report a reproducible Tradebot bug
labels: bug
---

## Bug summary

Describe the bug clearly.

## Area affected

- [ ] Market feed / stale data
- [ ] Contract resolution
- [ ] Strategy output
- [ ] Execution gate
- [ ] Review queue
- [ ] Risk controls
- [ ] Dashboard
- [ ] Reports / reconciliation
- [ ] ML/RL/data workflow
- [ ] CI / tests
- [ ] Documentation

## Expected behavior

What should have happened?

## Actual behavior

What happened instead?

## Reproduction steps

```bash
# Paste the minimum commands needed to reproduce.
```

## Validation already tried

```bash
PYTHONPATH=. pytest -q
PYTHONPATH=. python -m core.health_gate --desk DEFAULT --strict
```

## Logs or screenshots

Attach only redacted logs/screenshots. Do not include private config, broker credentials, account IDs, or live sensitive trading data.

## Impact

- [ ] Blocks local development
- [ ] Blocks CI
- [ ] Blocks dashboard use
- [ ] Blocks paper trading
- [ ] Could affect live-market readiness
- [ ] Cosmetic only

## Notes

Add any suspected root cause, changed file, branch, or related PR.
