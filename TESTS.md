# Test Policy

## Default test gate (CI-safe)

Run this in local dev and CI:

```bash
PYTHONPATH=. pytest -q
```

This suite is intended to be deterministic and offline-safe (no live broker/network dependency).

## Integration tests (network/secrets)

Use `@pytest.mark.integration` only for tests that require one or more of:

- live network access
- real broker/API credentials
- external infrastructure

By default, integration tests should be excluded from the main unit gate and run explicitly:

```bash
PYTHONPATH=. pytest -q -m integration
```

Current status:

- Unit/default suite: active
- Integration-marked tests: none required at this time

## Deterministic daily regression suite

Daily local regression (offline-safe) runs both the test suite and strict health gate:

```bash
PYTHONPATH=. ./scripts/run_daily_regression.sh
```

Artifacts:

- `logs_dir()/health_gate_report.json`
- `logs_dir()/health_gate_report.md`
- `logs_dir()/daily_regression/YYYY-MM-DD.json`

Health gate includes `ONE_TRADE_CAN_BUILD`:

- synthetic index + option ticks are injected
- deterministic token resolution is exercised
- one candidate must reach executable state (`final_action != ADVISORY_ONLY`)
- blocked statuses `STALE_OPTION_LTP`, `NO_TOKEN`, `FEED_UNKNOWN` fail the gate
