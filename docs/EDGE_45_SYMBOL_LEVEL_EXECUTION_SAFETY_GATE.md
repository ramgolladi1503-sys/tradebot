# EDGE-45 — Symbol-Level Execution Safety Gate

## Purpose

EDGE-45 adds a read-only symbol-level execution safety gate.

EDGE-43 created canonical feed-health truth. EDGE-45 uses that truth at executable-candidate level so a candidate cannot be executable when its specific symbol has unsafe feed evidence.

This closes the gap where global/candidate execution truth could be clean while the target symbol had stale option ticks, blocked option feed evidence, subscription failure, miss-ing symbol identity, or global feed/websocket unsafe evidence.

## Implementation

### `core/symbol_execution_safety.py`

Adds:

- `SymbolExecutionSafetyDecision`
- `resolve_candidate_symbol()`
- `classify_symbol_execution_safety()`

The gate resolves candidate symbol identity from direct candidate fields first, then source flags:

- `symbol`
- `underlying`
- `underlying_symbol`
- `index_symbol`

It builds a feed-health payload from candidate/source-flag/runtime feed evidence and calls:

```python
classify_feed_health_truth(payload, symbols=(symbol,))
```

The symbol list is explicit and authoritative. The classifier does not auto-expand to other symbols for execution gating.

### `core/executable_truth.py`

`classify_executable_truth()` now consumes the symbol safety gate and stores the result under:

```python
context["symbol_execution_safety"]
```

If symbol safety is unsafe, executable truth appends:

- `symbol_execution_safety_failed`
- symbol-specific safety reasons

## Stable reason codes

- `symbol_missing`
- `symbol_feed_unsafe`
- `symbol_subscription_failed`
- `symbol_stale_option_ticks`
- `symbol_option_feed_blocked`

## Tests

`tests/test_edge45_symbol_execution_safety.py` proves:

- direct symbol resolution wins
- clean symbol feed passes
- missing symbol fails closed
- stale symbol option ticks block
- global feed unsafe blocks symbol execution
- subscription failure is preserved
- executable truth blocks stale symbol feed
- executable truth stays clean when all symbol/feed/quote/spread/signal evidence is clean

Run:

```bash
PYTHONPATH=. python -m pytest tests/test_edge45_symbol_execution_safety.py
```

## Safety

- No broker imports
- No broker calls
- No order placement
- No modify/cancel/exit behavior
- No websocket reconnects
- No subscription mutation
- No runtime mutation
- No dashboard work
- No strategy tuning
- No threshold loosening

This is a read-only execution safety contract only.

## Out of scope

- Dashboard visualization
- Runtime recovery behavior
- Candidate status cleanup
- Ranking/scoring truth hardening
- Live order enablement
