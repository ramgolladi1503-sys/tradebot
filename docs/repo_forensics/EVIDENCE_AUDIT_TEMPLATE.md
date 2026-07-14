# Evidence Audit Report Template

## Purpose

Validate whether TradeBot evidence files prove real decisions instead of decorating the repo with weak status fields.

Evidence must explain what happened, why it happened, whether it was an order action, and whether any broker API was called.

## Required Evidence Fields

| Field | Required When | Status |
|---|---|---|
| `mode` | all decision/evidence records | PASS / FAIL / UNKNOWN |
| `candidate_id` | candidate/trade decision records | PASS / FAIL / UNKNOWN |
| `decision` | all decision records | PASS / FAIL / UNKNOWN |
| `reason` | all block/allow decisions | PASS / FAIL / UNKNOWN |
| `timestamp` | all runtime evidence | PASS / FAIL / UNKNOWN |
| `i-s_order_action` | read-only/order-adjacent evidence | PASS / FAIL / UNKNOWN |
| `b-roker_api_called` | paper/live/order-adjacent evidence | PASS / FAIL / UNKNOWN |
| `source` | generated evidence/report files | PASS / FAIL / UNKNOWN |

## Evidence Sources Reviewed

| Path | Type | Status | Notes |
|---|---|---|---|
| TBD | JSON / JSONL / MD | PASS / FAIL / UNKNOWN | TBD |

## Findings

### EVIDENCE-ID

| Field | Value |
|---|---|
| Severity | TBD |
| Evidence Path | TBD |
| Missing Field | TBD |
| Status | OPEN / RESOLVED / UNKNOWN |

#### Evidence

```text
Observed payload/report snippet or absence of required field.
```

#### Impact

```text
Why this weakens traceability or creates fake confidence.
```

#### Recommendation

```text
Minimal evidence contract improvement.
```

#### Proof Required

```text
Contract test or generated evidence proving the field exists and is meaningful.
```

## Weak Evidence Examples

Bad evidence:

```json
{"stat-us": "ok", "sa-fe": true}
```

Good evidence:

```json
{
  "mode": "PAPER",
  "candidate_id": "NIFTY_001",
  "decision": "BLOCKED",
  "reason": "FALLBACK_DATA_NOT_EXECUTABLE",
  "is_order_action": false,
  "broker_api_called": false
}
```

## Scope Guard

- Do not create fake runtime evidence manually.
- Do not treat manually written notes as runtime proof.
- Do not hide missing fields.
