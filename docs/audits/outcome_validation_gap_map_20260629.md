# Outcome Validation Gap Map

## What exists

| Artifact | Current State |
| --- | --- |
| `core/candidate_outcome_contract.py` | Explicit outcome contract exists |
| `core/candidate_finalization.py` | Candidate truth can be mirrored into lifecycle / execution metadata |
| Replay / proof pack modules | Present, but not yet enough to prove edge end to end |
| Strategy hypothesis contracts | Present, with required outcome metrics |

## What is missing

| Missing Evidence | Required Artifact | Current File / Module | Gap | Priority |
| --- | --- | --- | --- | --- |
| Outcome-linked strategy proof | Per-strategy replay report | replay / proof pack path | No durable edge claim yet | High |
| Cost-aware validation | Slippage, spread, theta, fees | outcome contract / replay | Not uniformly validated | High |
| Horizon-defined probability proof | event, horizon, target, stop, calibration | `core/candidate_outcome_contract.py` | Some labels lack full provenance | High |
| Live paper linkage | Candidate -> future outcome trace | paper telemetry / outcome journal | Not complete enough for proof | High |
| Per-regime validation | Regime-specific expectancy tables | replay modules | Needed for real edge claims | High |

## Classification

| Condition | Classification |
| --- | --- |
| Has explicit event, horizon, target, stop, cost model, and calibration source | VALIDATED_OUTCOME_CONTRACT |
| Has score or confidence without full contract | HEURISTIC_SCORE_ONLY |
| Uses probability-style wording without full provenance | MISLEADING_PROBABILITY_LABEL |
| Cannot link to a future outcome trace | OUTCOME_CONTRACT_MISSING |
| Has contract but no calibration source | CALIBRATION_MISSING |

## Bottom line

The repo has the bones of outcome validation, but not yet the evidence density required to claim edge.
