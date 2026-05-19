# Safety Boundary Report Template

## Purpose

Verify that TradeBot safety boundaries remain intact across SIM, PAPER, and LIVE behavior.

This report is static/read-only. It must not place orders, call brokers, run live trading code, or mutate runtime state.

## Boundary Summary

| Boundary | Status | Evidence | Notes |
|---|---|---|---|
| SIM -> broker placement impossible | PASS / FAIL / UNKNOWN | TBD | TBD |
| PAPER -> real broker placement impossible | PASS / FAIL / UNKNOWN | TBD | TBD |
| LIVE requires explicit readiness | PASS / FAIL / UNKNOWN | TBD | TBD |
| Dashboard order action unreachable unless scoped | PASS / FAIL / UNKNOWN | TBD | TBD |
| Read-only paths keep `is_order_action=false` | PASS / FAIL / UNKNOWN | TBD | TBD |
| Broker API call evidence is explicit | PASS / FAIL / UNKNOWN | TBD | TBD |

## Safety Findings

### SAFETY-ID

| Field | Value |
|---|---|
| Severity | CRITICAL / HIGH / MEDIUM / LOW / UNKNOWN |
| Boundary | TBD |
| File | TBD |
| Status | OPEN / RESOLVED / UNKNOWN |

#### Evidence

```text
Forbidden import, unsafe flag, missing gate, or unproven boundary.
```

#### Impact

```text
Explain how this could cause unsafe behavior.
```

#### Recommendation

```text
Minimal safe fix or proof required.
```

#### Proof Required

```text
Required test/evidence to close the finding.
```

## Forbidden Pattern Checklist

- [ ] No paper module imports live broker placement.
- [ ] No SIM module imports live broker placement.
- [ ] No read-only module sets `is_order_action=true`.
- [ ] No read-only module sets `broker_api_called=true`.
- [ ] No dashboard path exposes submit/modify/cancel/exit actions unless explicitly scoped.
- [ ] LIVE mode does not default on.
- [ ] LIVE mode requires explicit readiness flags.

## Scope Guard

- Static review only.
- No broker calls.
- No live runtime execution.
- No target repo mutation by the scanner.
