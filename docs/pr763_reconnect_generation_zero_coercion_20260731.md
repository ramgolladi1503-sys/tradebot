# PR #763 Reconnect Generation Zero-Coercion Audit - 2026-07-31

## Scope

Worktree: `/Users/madhuram/tradebot-unified-live-validation-pr748-756-v1`

Branch: `campaign/unified-live-validation-pr748-756-v1`

Starting HEAD: `2d6fed2aceb9ec04ecc3d0555156ff753ec62770`

Prior bounded run: `unified-pr748-756-20260731-6eeff73e5605-live-21c57722`

Prior verdict: `CALLBACK_FIX_WORKS_CONTEXT_REJECTED_BY_RECONNECT_GENERATION`

## Proven Root Cause

The prior sealed bounded proof showed:

- NIFTY raw full callbacks: `6`
- constituent raw full callbacks: `98`
- NIFTY `exchange_timestamp`: present
- observation plan: active
- feed reconnect generation: `0`
- packet rejection: `CALLBACK_SEEN_GENERATION_MISMATCH`

The live path treated a valid generation `0` as missing by using falsey fallback logic:

```python
int(observation_state.get("reconnect_generation") or -1)
```

For generation `0`, this evaluates to `-1`, causing a false mismatch against feed generation `0`.

## Helper

The repair adds an explicit helper in `core.kite_depth_ws`:

```python
def _coerce_generation(value: object, *, default: int = -1) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
```

This preserves `0` as a valid generation and fails closed for missing or invalid values.

## Corrected Locations

### `core/kite_depth_ws.py` - `_record_observation_callback_truth`

Old expression:

```python
int(observation_state.get("reconnect_generation") or -1) == int(feed_identity.get("reconnect_generation") or 0)
```

New expression:

```python
plan_generation = _coerce_generation(observation_state.get("reconnect_generation"), default=-1)
feed_generation = _coerce_generation(feed_identity.get("reconnect_generation"), default=-1)
reconnect_generation_matches = plan_generation == feed_generation
```

Zero is valid: yes. This is the raw callback truth path that decides whether an otherwise valid observation callback belongs to the current feed reconnect generation.

### `core/kite_depth_ws.py` - `on_ticks` / `observation_token_allowed`

Old expression:

```python
int(observation_state.get("reconnect_generation") or -1) == int(_FEED_RECONNECT_GENERATION)
```

New expression:

```python
plan_generation = _coerce_generation(observation_state.get("reconnect_generation"), default=-1)
feed_generation = _coerce_generation(_FEED_RECONNECT_GENERATION, default=-1)
plan_generation == feed_generation
```

Zero is valid: yes. This is the accepted observation/shadow-bar publication gate.

## Audit Search

Searched campaign/runtime paths for:

```text
reconnect_generation") or -1
generation") or -1
socket_generation") or -1
reconnect_generation.*or -1
socket_generation.*or -1
generation.*or -1
```

Result after repair:

```text
no remaining matches in core, scripts, or tests
```

No unrelated numeric defaults were changed.

## Tests

Added deterministic regressions in `tests/test_kite_depth_ws_observation_on_ticks.py` proving:

- generation `0` matches feed generation `0`;
- generation `1` matches feed generation `1`;
- generation `0` does not match feed generation `1`;
- missing generation does not silently become `0`;
- invalid generation fails closed;
- generation `0` allows an otherwise-valid NIFTY full callback;
- generation `0` allows an otherwise-valid equity full callback;
- accepted full callbacks record full-payload evidence;
- `observation_token_allowed` accepts generation `0 == 0`;
- stale-generation callbacks remain rejected;
- no execution/order capability is introduced by the lifecycle evidence path.

Focused observation test result before full suite:

```text
34 passed
```

## Safety Boundary

This repair does not change reconnect-generation ownership, generation increment behavior, socket ownership, feed session identity, subscription semantics, mode semantics, strategy logic, risk gates, execution gates, or feed gates.
