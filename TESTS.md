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
