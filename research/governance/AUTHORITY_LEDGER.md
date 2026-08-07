# Authority Ledger

The Authority Ledger is the auditable record of how research authority changes over time. It is distinct from the Claim Registry: the claim record describes current state; the ledger preserves each authority transition.

## Ledger Entry Schema

Each entry must contain:

- Ledger entry ID or Decision ID
- Claim ID and version
- Timestamp
- Prior lifecycle state
- New lifecycle state
- Prior authority grade
- New authority grade
- Observation Authority status
- Data Authority status
- Information Authority status
- Mechanism Authority status
- Statistical Authority status
- Economic Authority status
- Independent Attack status
- Evidence IDs considered
- Calibration IDs considered
- Decision rationale
- Blocking weaknesses
- Review trigger
- Reviewer / decision authority

## Rules

- Ledger history is append-only in scientific meaning. Corrections create correcting entries rather than erasing prior decisions.
- An authority increase requires evidence-promotion compliance.
- An authority decrease may be triggered immediately by invalidation, failed reproduction, contradictory evidence, calibration failure, or supersession.
- Current authority must be derivable from the latest valid ledger entry plus any subsequent invalidation or supersession records.

Sprint-001 specifies this ledger contract. A machine-enforced ledger implementation is not claimed in this sprint.
