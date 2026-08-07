# MROS Registries

Registries provide durable identity, provenance, lineage, and auditability for research objects.

## Required ID Families

- `CLAIM-YYYY-NNNN`
- `EXP-YYYY-NNNN`
- `DATA-YYYY-NNNN`
- `EVID-YYYY-NNNN`
- `CAL-YYYY-NNNN`
- `DEC-YYYY-NNNN`

IDs are immutable. Versions may advance, but an ID may not be reused for a materially different object.

## Registry Directories

- `claims/` — scientific statements and lifecycle state
- `experiments/` — procedures, hypotheses tested, and outcomes
- `datasets/` — provenance, coverage, transformations, and integrity
- `evidence/` — artifacts supporting, contradicting, or invalidating claims
- `calibration/` — certifier calibration runs and operating characteristics
- `decisions/` — promotion, rejection, invalidation, supersession, and governance decisions

## Machine-Readable Future

Sprint-001 defines schemas in Markdown. A later sprint may add machine-enforced serialization and validation, but that implementation is not claimed here.
