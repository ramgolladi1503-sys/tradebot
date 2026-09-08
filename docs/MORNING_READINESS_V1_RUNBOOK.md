# Morning Readiness V1 runbook

## Current certified scope

The exact base release is `e1f803d9f56c60b9208ac686db8da8ddba055b4d`.
The state-machine dry run is offline and read-only. It does not start a live
observer, authenticate with Kite, or enable execution authority.

Run:

```bash
PYTHONPATH=. python scripts/morning_readiness_dry_run.py
PYTHONPATH=. pytest -q tests/test_morning_readiness_v1.py
```

## Safety boundary

`broker_write_authority=false`, `order_authority=false`,
`paper_authorized=false`, and `live_authorized=false` are required.

Do not edit source, switch branches, reuse evidence roots, or tune queues after
an observer reaches `PREOPEN_ARMED`. Option-feed, ranking, and strategy
failures may enter `LIVE_DEGRADED`; storage or evidence-integrity failures must
fail closed.

## Certification boundary

This runbook is not a claim that the one-command morning launcher, automatic
EOD drain/seal, independent verifier, or mutation campaign is implemented.
Those gates must pass before `NEXT_LIVE_SESSION_READY=true` can be issued.
