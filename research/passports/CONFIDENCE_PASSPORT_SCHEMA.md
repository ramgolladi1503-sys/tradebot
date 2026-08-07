# Confidence Passport Schema

Every certified claim must carry a confidence passport. The passport is a structured explanation of why the claim currently deserves its authority and what could reduce it.

## Identity

- Claim ID
- Claim version
- Lifecycle state
- Authority grade
- Passport version
- Last review timestamp

## Authority Dimensions

### Observation Authority
What was directly observed, from which Evidence IDs, with what reproducibility status?

### Data Authority
Which Dataset IDs support the claim, and what defects, exclusions, coverage limits, or provenance weaknesses remain?

### Information Authority
What evidence shows predictive or explanatory information exists beyond a tuned strategy representation? State stability and degradation evidence.

### Mechanism Authority
What mechanism is claimed, what evidence distinguishes it from alternatives, and what remains merely correlational?

### Statistical Authority
What uncertainty, power, multiplicity, selection, representation, and null-world evidence applies? Reference Calibration IDs where required.

### Economic Authority
What evidence supports net economic value after realistic costs, slippage, liquidity, capacity, timing, and execution assumptions?

### Independent Attack
Reference attack artifacts, attack scope, successful attacks, failed attacks, and unresolved critical concerns.

## Known Weaknesses
List all material weaknesses that remain compatible with the current lifecycle state.

## Review Trigger
Define events that force re-review, including data revisions, regime shifts, material performance degradation, mechanism contradiction, implementation changes, or new contradictory evidence.

## Confidence
Provide calibrated confidence only when a calibration basis exists. Otherwise state `UNcalibrated` or equivalent rather than inventing a probability.

## Decision Lineage
List Decision IDs responsible for current state and any supersession chain.
