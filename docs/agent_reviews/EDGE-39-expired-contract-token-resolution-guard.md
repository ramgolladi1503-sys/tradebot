# EDGE-39 - Expired Contract Token Resolution Guard

mode: PAPER
candidate_id: EDGE-39
source: docs/agent_reviews/EDGE-39-expired-contract-token-resolution-guard.md
timestamp: 2026-05-22T20:07:00+05:30
decision: reject expired option contracts during token resolution before they can become execution-grade candidates
reason: May 22 diagnostic evidence showed an expired option expiry could poison token resolution and downstream candidate truth
is_order_action: false
broker_api_called: false
live_order_action: false
broker_order_action: false

## Agent Work Contract

### Scope

Add a fail-closed guard in option token resolution and instrument expiry selection so expired requested expiries and expired resolved fallback contracts cannot return execution-grade token payloads.

### Files changed

- `core/instruments.py`
- `core/option_token_resolver.py`
- `tests/test_instruments_expiry_fail_closed.py`
- `tests/test_option_token_resolver_expired_contract_guard.py`
- `docs/EDGE_TODO.md`
- `docs/agent_reviews/EDGE-39-expired-contract-token-resolution-guard.md`

### Out of scope

- No quote timestamp or age consistency guard. That is EDGE-40.
- No fallback execution firewall beyond expired fallback contract rejection. That is EDGE-41.
- No feed recovery wiring. That is EDGE-44.
- No strategy rewrite.
- No dashboard changes.

## Grill Me Review

### Hard questions

1. Does this fix all token-resolution quality problems?
   - No. It fixes expired contract selection only. Cache freshness and broader token coverage remain separate problems.

2. Does this fix fallback rows appearing in the UI?
   - No. It only prevents expired fallback contracts. General fallback execution firewall is EDGE-41.

3. Can this hide a valid current-week contract?
   - The guard only rejects expiry dates earlier than the current IST trading date. Same-day expiry is still allowed.

4. Can an expired exact local-cache match still return execution_grade=true?
   - No. Expired requested expiry is rejected before loading instruments, and exact-match payloads include expiry evidence.

5. Does this call broker APIs?
   - No. The change is limited to pure token/instrument resolver guard logic and tests with monkeypatched instrument data.

## Hermes Review

### Boundary review

- `broker_api_called=false`
- `is_order_action=false`
- `live_order_action=false`
- `broker_order_action=false`
- No execution modules changed.
- No strategy modules changed.
- No dashboard modules changed.
- No runtime startup behavior changed.

### Files not touched

- `core/opportunity_engine.py`
- `core/review_queue.py`
- `core/entry_semantics.py`
- `core/execution_engine.py`
- `dashboard/*`
- `strategies/*`

## GSD Review

### What this improves

- Expired requested expiry returns `None` immediately.
- Expired local exact matches cannot become execution-grade.
- Safe nearest fallback skips expired contracts.
- Expired fallback candidates return `None` if no future contract exists.
- `select_expiry()` no longer selects the last expired expiry when all expiries are old.
- `resolve_registry_contract()` fails closed when requested or selected expiry is expired.
- Rejection event includes `EXPIRED_CONTRACT_SELECTED` evidence.
- TODO list removes EDGE-39 after implementation.

### What this does not improve

- Does not prove strategy edge.
- Does not repair stale quote age mismatches.
- Does not centralize quote truth.
- Does not eliminate all fallback telemetry.

## Scope Guard

The change is narrow: only instrument expiry selection, option token resolution, focused tests, TODO, and evidence docs changed.

## QA / Safety Review

### Tests added

- Expired requested expiry is rejected before instrument cache lookup.
- Expired local exact match returns `None`.
- Valid future exact match remains execution-grade.
- Safe fallback skips expired contracts and can choose a future fallback.
- Safe fallback returns `None` when only expired contracts exist.
- Expired rejection event contains non-action evidence fields.
- `select_expiry()` returns `None` when all expiries are expired.
- `select_expiry()` allows same-day expiry.
- `resolve_registry_contract()` rejects expired requested expiry.
- `resolve_registry_contract()` does not fallback to expired expiry when only old expiries exist.
- `resolve_registry_contract()` selects future expiry when available.

### Commands to run locally

```bash
pytest tests/test_option_token_resolver_expired_contract_guard.py tests/test_instruments_expiry_fail_closed.py -q
```

## Acceptance Proof

Acceptance requires:

- Focused tests pass.
- No expired contract can return an execution-grade token payload.
- Same-day and future expiries remain valid.
- Expired rejection evidence includes `EXPIRED_CONTRACT_SELECTED`.
- Existing token coverage behavior remains unchanged except for expired-date rejection.

## Runtime Proof Required After Merge

After merge, run token resolver or evidence replay against the May 22 diagnostic context and confirm expired contracts are classified as rejected rather than valid resolution.

Required runtime proof:

- No selected token payload has `resolved_expiry` earlier than trading date.
- Expired requested expiry logs `OPTION_TOKEN_EXPIRED_CONTRACT_REJECTED`.
- Valid future exact contract still resolves normally.

## What This PR Does Not Prove

This PR does not prove live trading readiness, strategy profitability, quote freshness correctness, fallback firewall completeness, broker readiness, dashboard correctness, or paper-trading expectancy.

It only proves expired option contracts fail closed during token resolution.

## Human Approval

Human approval required before merge: confirm CI is green and focused tests pass locally or in CI.


## High-Risk Path Review

N/A

## Evidence Contract

- mode: SIM
- candidate_id: N/A
- decision: PASS
- reason: Agent review complete
- timestamp: 2026-07-14T00:00:00Z
- is_order_action: false
- broker_api_called: false
- source: agent_review
- live_order_action: false
- broker_order_action: false
