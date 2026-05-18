# PR #80 — Option Resolver Fail-Closed Fix

## Scope

Make option contract resolution deterministic, safe, and non-crashing.

## Files to change

- `core/option_token_resolver.py`
- `tests/test_option_token_resolver.py`

## Required behavior

- Exact contract match returns an execution-grade resolution.
- Safe nearest fallback remains visible but is advisory-only.
- No fallback returns a blocked resolution instead of crashing.
- Option token not-found path is reachable and logged.
- Coverage below minimum remains blocked via `TokenCoverageError`.

## Do not touch

- strategies
- dashboard
- ranking
- scoring
- live execution
- broker order calls

## Test commands

```bash
PYTHONPATH=. pytest -q tests/test_option_token_resolver.py
PYTHONPATH=. pytest -q
```
