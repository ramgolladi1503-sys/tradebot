# Full Pytest Shim Migration Plan

## Purpose

`core/full_pytest_contracts.py` was introduced as a temporary stabilization layer to keep the full local/CI pytest suite green while the project moved out of compatibility-hook debt.

It should not become permanent architecture.

This document scopes the migration path for moving each temporary behavior into the real owning module, then deleting the shim.

## Why This Exists

The bot recently stabilized depth ownership, stale-prune behavior, and local full pytest. During that work, three non-depth problems were exposed:

1. non-live startup warmup could degrade before reaching the configured long lookback window;
2. advisory REST fallback quote truth could be overwritten or fetched repeatedly during rate-limited revalidation;
3. long-run torture replay could fail on a single local scheduler latency spike even when p95/avg latency and functional integrity were clean.

The shim fixed those contracts quickly, but temporary monkeypatch-style stabilization is not the final design.

Real behavior belongs in real modules:

```text
core/market_data.py
core/review_queue.py
core/torture_test.py
```

## Current Temporary Shim

File:

```text
core/full_pytest_contracts.py
```

Installed from:

```text
sitecustomize.py
```

Current temporary contracts:

```text
1. market_data warmup long-lookback/fail-fast behavior
2. review_queue REST fallback quote preservation and rate limiting
3. torture_test long-run p95 latency gate
```

## Migration Rule

Do not delete `core/full_pytest_contracts.py` until all three behaviors are migrated into real modules and full pytest is green.

Do not migrate all three behaviors in one risky PR.

## Planned PR Sequence

### PR #48 — Document and isolate full-pytest shim debt

Purpose:

- document this migration plan;
- keep runtime behavior unchanged;
- prevent accidental permanent dependency on the shim;
- make the cleanup order explicit.

Validation:

```bash
PYTHONPATH=. pytest -q
```

### PR #49 — Move market_data warmup behavior into core/market_data.py

Owner module:

```text
core/market_data.py
```

Behavior to migrate:

- preserve explicit non-live fail-fast behavior when `NONLIVE_STARTUP_WARMUP_MAX_HIST_EMPTY_ATTEMPTS <= 1`;
- allow the dedicated long-lookback startup warmup path to reach the configured lookback window before degrading;
- keep warmup observability fields unchanged.

Important tests:

```bash
PYTHONPATH=. pytest -q tests/test_market_data_warm_seed.py
```

Acceptance:

- early-degrade test still makes one historical call;
- long-lookback test reaches the configured lookback window;
- full pytest remains green.

### PR #50 — Move torture long-run p95 gate into core/torture_test.py

Owner module:

```text
core/torture_test.py
```

Behavior to migrate:

- long-run stability should hard-fail on sustained latency, not one isolated max-latency outlier;
- `decision_latency_ms_max` remains recorded as telemetry;
- `decision_latency_ms_p95` becomes the long-run hard latency gate when functional integrity is clean.

Important tests:

```bash
PYTHONPATH=. pytest -q tests/test_torture_replay.py
```

Acceptance:

- long-run stability passes when p95 is below threshold and no functional violations exist;
- non-latency violations still fail;
- max latency remains visible in report metrics.

### PR #51 — Move review_queue REST fallback behavior into core/review_queue.py

Owner module:

```text
core/review_queue.py
```

Behavior to migrate:

- preserve better `rest_fallback` quote truth when revalidation cannot refresh live quote;
- rate-limit repeated advisory REST fallback calls for the same tradingsymbol;
- do not overwrite `PRICE_MISMATCH/rest_fallback` rows with worse `NO_LIVE_OPTION_FEED` rows during the cooldown window.

Important tests:

```bash
PYTHONPATH=. pytest -q tests/test_review_queue_live_entry.py
```

Acceptance:

- REST fallback is fetched once inside the cooldown window;
- second queue write reuses cached/previous fallback quote truth;
- quote source remains explicit as `rest_fallback`;
- no executable permission is granted from stale/rest fallback quote truth.

### PR #52 — Delete the temporary shim

Files to change:

```text
sitecustomize.py
core/full_pytest_contracts.py
```

Actions:

- remove `full_pytest_contracts.install()` from `sitecustomize.py`;
- delete `core/full_pytest_contracts.py`;
- run full pytest.

Acceptance:

```bash
PYTHONPATH=. python scripts/validate_depth_offmarket.py
PYTHONPATH=. pytest -q tests/test_depth_subscription_tokens.py
PYTHONPATH=. pytest -q tests/test_stale_option_prune_hysteresis.py
PYTHONPATH=. pytest -q tests/test_market_data_warm_seed.py
PYTHONPATH=. pytest -q tests/test_review_queue_live_entry.py
PYTHONPATH=. pytest -q tests/test_torture_replay.py
PYTHONPATH=. pytest -q
```

## Hard Rules

1. Do not touch depth ownership during this migration.
2. Do not weaken execution gates.
3. Do not convert REST fallback into executable quote truth.
4. Do not remove max-latency telemetry from torture reports.
5. Do not hide warmup degradation; preserve observability.
6. Do not delete the shim until the real module behavior is proven.

## Definition of Done

The shim migration is done only when:

```text
core/full_pytest_contracts.py no longer exists
sitecustomize.py no longer imports it
market_data/review_queue/torture_test own the behavior directly
all targeted tests pass
full pytest passes
CI is green
```
