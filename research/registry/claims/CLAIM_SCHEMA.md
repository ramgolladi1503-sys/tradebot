# Claim Registry Schema

Each claim record must contain:

- Claim ID
- Version
- Title
- Exact falsifiable statement
- Lifecycle state
- Claim type: observation / information / mechanism / statistical / economic / operational
- Population and market scope
- Target variable
- Forecast or causal horizon
- Inclusion and exclusion boundaries
- Prior belief or rationale
- Proposed mechanism, if any
- Destroyers
- Assumptions
- Supporting Evidence IDs
- Contradicting Evidence IDs
- Experiment IDs
- Dataset IDs
- Calibration IDs
- Decision IDs
- Supersedes / superseded by
- Known weaknesses
- Review triggers
- Authority grade
- Confidence passport path, when applicable
- Owner
- Created timestamp
- Last review timestamp

A claim statement may not be silently rewritten. Material semantic changes require a new version and, when meaning changes substantially, a new Claim ID with lineage.
