# Flow Wiring Report Template

## Purpose

Verify whether the configured TradeBot runtime flow is statically connected from entrypoints to downstream decision/evidence paths.

This report must not execute live runtime code.

## Metadata

| Field | Value |
|---|---|
| Branch | TBD |
| Commit | TBD |
| Entrypoint | TBD |
| Config | `.gsd-forensics.yaml` |

## Expected Flow

```text
auth
  -> feed
  -> instrument_resolution
  -> market_validation
  -> candidate_generation
  -> no_trade
  -> ranking
  -> risk
  -> execution_boundary
  -> evidence
```

## Flow Step Status

| Step | Status | Evidence | Notes |
|---|---|---|---|
| auth | PASS / FAIL / UNKNOWN | TBD | TBD |
| feed | PASS / FAIL / UNKNOWN | TBD | TBD |
| instrument_resolution | PASS / FAIL / UNKNOWN | TBD | TBD |
| market_validation | PASS / FAIL / UNKNOWN | TBD | TBD |
| candidate_generation | PASS / FAIL / UNKNOWN | TBD | TBD |
| no_trade | PASS / FAIL / UNKNOWN | TBD | TBD |
| ranking | PASS / FAIL / UNKNOWN | TBD | TBD |
| risk | PASS / FAIL / UNKNOWN | TBD | TBD |
| execution_boundary | PASS / FAIL / UNKNOWN | TBD | TBD |
| evidence | PASS / FAIL / UNKNOWN | TBD | TBD |

## Wiring Findings

### WIRING-ID

| Field | Value |
|---|---|
| Severity | TBD |
| Flow Step | TBD |
| File | TBD |
| Status | PASS / FAIL / UNKNOWN |

#### Evidence

```text
Static reference, import path, script command, or absence of caller.
```

#### Impact

```text
Explain runtime risk.
```

#### Proof Required

```text
What proves this step is correctly wired?
```

## Unknowns

Unknowns must not be treated as safe.

| Flow Step | Why Unknown | Required Proof |
|---|---|---|
| TBD | TBD | TBD |

## Scope Guard

- Static review only.
- No live runtime execution.
- No broker calls.
- No product behavior changed.
