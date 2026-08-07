# Experiment Registry Schema

Each experiment record must contain:

- Experiment ID
- Version
- Linked Claim ID(s)
- Research question
- Predeclared hypothesis and null
- Population and time range
- Dataset IDs
- Input fields and representations
- Transformations
- Label/outcome definition
- Time-causality rules
- Leakage controls
- Train/development/validation/holdout boundaries, when applicable
- Parameter and search space
- Multiplicity/search context
- Primary metric(s)
- Secondary metric(s)
- Power/sample-size considerations
- Negative controls / null worlds, when applicable
- Procedure or code reference
- Environment assumptions
- Random seeds, when applicable
- Output artifact paths
- Evidence IDs produced
- Deviations from plan
- Result status: completed / failed / invalidated / aborted
- Reproduction status
- Owner
- Start and completion timestamps

Unreported deviations are a governance failure. A failed or invalidated experiment remains registered.
