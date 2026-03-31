# Phase 2 → Phase 3 Integration (MANDATORY PATCHES)

These patches must be applied manually to complete production-safe wiring.

## 1. Freeze at opportunity_engine

Add after `selected` computation:

```python
from core.execution_intent import attach_execution_intent, clear_execution_intent

if selected:
    updated = attach_execution_intent(updated)
else:
    updated = clear_execution_intent(updated)
```

## 2. Kill late promotion

Replace `_maybe_promote_execute_candidate` with:

```python
def _maybe_promote_execute_candidate(candidate, *args, **kwargs):
    if not candidate.get("execution_intent"):
        return candidate
    return candidate
```

## 3. Remove emit-time rescoring

Ensure scoring only happens once in Phase 2.

## 4. Enforce fail-closed execution

Before execution:

```python
if not candidate.get("execution_intent"):
    return
```

---

## Outcome

- Phase 2 becomes single source of truth
- Phase 3 becomes execution-only
- Queue becomes read-only projection

Without this, system is NOT production safe.
