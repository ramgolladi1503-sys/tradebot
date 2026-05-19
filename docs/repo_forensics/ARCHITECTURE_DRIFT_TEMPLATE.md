# Architecture Drift Report Template

## Purpose

Detect stale, duplicate, conflicting, or partially replaced implementations that create fake stability.

Architecture drift is especially dangerous in TradeBot because a newer module can pass tests while an older runtime path remains active.

## Drift Summary

| Area | Status | Evidence | Notes |
|---|---|---|---|
| duplicate modules | PASS / FAIL / UNKNOWN | TBD | TBD |
| old/new pipeline split | PASS / FAIL / UNKNOWN | TBD | TBD |
| stale dashboard readers | PASS / FAIL / UNKNOWN | TBD | TBD |
| stale docs | PASS / FAIL / UNKNOWN | TBD | TBD |
| multiple config owners | PASS / FAIL / UNKNOWN | TBD | TBD |
| unused critical modules | PASS / FAIL / UNKNOWN | TBD | TBD |

## Drift Findings

### DRIFT-ID

| Field | Value |
|---|---|
| Severity | TBD |
| Area | TBD |
| Files | TBD |
| Status | OPEN / RESOLVED / UNKNOWN |

#### Evidence

```text
Duplicate file/function/module/config/doc evidence.
```

#### Impact

```text
Why this can cause wrong runtime behavior or fake confidence.
```

#### Canonical Owner Decision Needed

```text
Which module/path should own the behavior?
```

#### Proof Required

```text
What proves the stale/duplicate path is removed, disabled, or correctly marked deferred?
```

## Common Drift Examples

- Ranking engine exists, but dashboard still reads raw emitted rows.
- New no-trade module exists, but production path uses legacy suppression.
- Evidence schema changed, but dashboard reads old JSON.
- Test suite protects old behavior that product no longer wants.
- Multiple config sources define mode/safety settings.

## Scope Guard

- This report identifies drift only.
- Do not delete modules in the drift audit PR unless explicitly scoped.
- Do not rewrite runtime behavior from this template alone.
