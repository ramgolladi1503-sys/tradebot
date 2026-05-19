# Test Reality Report Template

## Purpose

Classify TradeBot tests by the strength of proof they provide.

The goal is to separate real behavioral/safety evidence from fake confidence.

## Test Classes

| Class | Meaning |
|---|---|
| SHAPE_ONLY | Checks keys/classes/fields exist but not behavior. |
| UNIT_BEHAVIOR | Proves isolated deterministic behavior. |
| INTEGRATION_WIRING | Proves modules connect through intended path. |
| SAFETY_REGRESSION | Proves unsafe behavior is blocked. |
| RUNTIME_COMMAND | Proves startup command or script behavior without live side effects. |
| EVIDENCE_CONTRACT | Proves reports/logs contain required fields. |
| FAKE_CONFIDENCE | Test hides risk, over-mocks, or proves irrelevant behavior. |
| UNKNOWN | Test purpose/strength cannot be determined. |

## Summary

| Class | Count |
|---|---:|
| SHAPE_ONLY | 0 |
| UNIT_BEHAVIOR | 0 |
| INTEGRATION_WIRING | 0 |
| SAFETY_REGRESSION | 0 |
| RUNTIME_COMMAND | 0 |
| EVIDENCE_CONTRACT | 0 |
| FAKE_CONFIDENCE | 0 |
| UNKNOWN | 0 |

## Test Findings

| Test File | Class | Strength | Proves | Does Not Prove |
|---|---|---|---|---|
| TBD | TBD | Weak / Medium / Strong | TBD | TBD |

## Weak Test Examples

### TEST-ID

| Field | Value |
|---|---|
| Test File | TBD |
| Class | TBD |
| Severity | TBD |

#### Weakness

```text
Why this test does not prove enough.
```

#### Better Proof Required

```text
Specific behavior/negative test required.
```

## Required Negative Tests

| Area | Required Negative Test | Status |
|---|---|---|
| fallback data | fallback candidate cannot be executable | TBD |
| stale feed | stale feed blocks order intent | TBD |
| paper/live boundary | paper path cannot call broker placement | TBD |
| evidence | missing required evidence field fails contract | TBD |

## Scope Guard

- Do not weaken existing tests.
- Do not classify shape-only tests as strong.
- Do not hide failures with mocks.
