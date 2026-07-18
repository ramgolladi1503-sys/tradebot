# Threat Model

## Protected assets

- Frozen research evidence and hashes
- Deterministic certification verdicts
- Human approval records
- Broker and live runtime boundaries
- Secrets and model credentials
- Reproducibility metadata

## Primary threats and controls

- **Look-ahead and leakage:** AQ-22 through AQ-28.
- **Evidence tampering:** AQ-11 through AQ-20.
- **Unrealistic execution:** AQ-31 through AQ-40.
- **Overfitting and holdout abuse:** AQ-41 through AQ-50.
- **Agent hallucination or override:** AQ-51 through AQ-60.
- **Unauthorized promotion or runtime mutation:** AQ-01 through AQ-10 and AQ-61 through AQ-70.

## Trust boundary

The package reads evidence. It has no order, broker, feed, risk override, strategy mutation, shell execution, arbitrary database write, or Git write capability.
