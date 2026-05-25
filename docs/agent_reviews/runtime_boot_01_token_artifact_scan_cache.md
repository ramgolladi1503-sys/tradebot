# Agent Review Evidence — RUNTIME-BOOT-01 Token Artifact Scan Cache

## Agent Work Contract

### Goal

Remove the repeated repository artifact scan from the market-data hot path while preserving startup security.

### Files changed

- `core/security_guard.py`
- `docs/agent_reviews/runtime_boot_01_token_artifact_scan_cache.md`

### Evidence Contract Fields

mode: PAPER
candidate_id: RUNTIME_BOOT_01_TOKEN_ARTIFACT_SCAN_CACHE
decision: CACHE_CLEAN_REPOSITORY_SECURITY_SCAN
reason: Runtime evidence showed repeated market-data calls entering a slow repository scan; the fix caches clean scan results and keeps startup security strict.
timestamp: 2026-05-25T06:17:45Z
is_order_action: false
broker_api_called: false
source: docs/agent_reviews/runtime_boot_01_token_artifact_scan_cache.md

### Non-goals

- No strategy changes.
- No feed ranking changes.
- No broker calls.
- No order behavior.
- No live execution behavior.
- No websocket lifecycle changes.
- No dashboard work.

## Scope Guard

Confirmed limited to `core/security_guard.py` and this evidence file.

Confirmed not touched:

- strategy logic
- order execution
- broker adapters
- websocket lifecycle
- candidate scoring
- feed gates
- dashboard UI

The implementation keeps unsafe repository artifacts fail-closed. Only clean scan results are cached process-locally.

## Grill Me Review

### Pushback

The previous behavior allowed a security check to run from repeated runtime credential resolution. Evidence showed this path was reachable from `kite_client.ltp()` during live market data fetches. A clean scan took about 13.949 seconds locally, which is unacceptable inside a market loop.

### Required proof

- First clean scan completes.
- Repeated scan returns from cache.
- Startup security can force a fresh scan.
- Unsafe artifacts still raise and are not silently ignored.
- No trading behavior is loosened.

## Hermes Review

### Contract clarity

The cache is process-local and keyed by resolved repository root. It does not persist a security decision across process restarts.

### Serialization / compatibility

No runtime JSON schema is changed. No evidence schema is changed. No order or broker payload is changed.

### Failure behavior

Unsafe artifact discovery still raises the existing runtime error message. Unsafe states are not cached.

## GSD Review

### Minimality

The PR changes the smallest boundary responsible for the stall: repository artifact scanning inside `core/security_guard.py`.

### Determinism

Clean scan cache behavior is deterministic within a process. `force_rescan=True` gives startup callers a deterministic fresh scan.

### Operational impact

Local proof:

```text
before: elapsed_sec=13.949
after_first_scan_sec=0.035
after_cached_scan_sec=0.00007
```

This removes a hidden multi-second filesystem walk from repeated market-data credential resolution.

## QA / Safety Review

Local tests run:

```bash
PYTHONPATH=. python -m pytest tests/test_runtime_safety_boot_guard.py tests/test_security_guard.py -q
```

Result:

```text
14 passed in 0.41s
```

Timing proof run locally:

```text
first_sec: 0.035
second_sec: 0.00007
```

Safety assertions:

- Security detection is not deleted.
- Startup can still force a scan.
- Clean result cache is process-local.
- Cache resets when writing a new local token.
- Runtime/generated folders are excluded from recursive scanning.

## Acceptance Proof

The PR is acceptable only if:

- Agent Review Evidence Gate passes.
- Existing security/runtime safety tests pass.
- No generated `runtime/evidence/` files are committed.
- The diff remains limited to the security guard and this evidence file.

## Runtime Proof Required After Merge

After merge, run PAPER live-market again and confirm:

- Runtime no longer stalls inside `security_guard.py -> find_repo_token_artifacts`.
- Runtime proceeds beyond `KITE_REST` into live monitoring cycles.
- Fresh feed/runtime artifacts are generated.
- No broker orders are placed.

## What This PR Does Not Prove

- It does not prove websocket recovery.
- It does not prove strategy edge.
- It does not prove profitable trades.
- It does not prove feed freshness is healthy.
- It does not prove candidate quality.
- It only proves the discovered repository scan stall is removed from repeated hot-path access after a clean scan.

## Human Approval

Proceed only if CI is green and the PR remains scoped to removing the repository scan from repeated runtime hot paths while preserving startup security.
