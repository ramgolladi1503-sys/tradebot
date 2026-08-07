# Calibration Registry Schema

Each calibration record must contain:

- Calibration ID
- Version
- Certifier or test procedure under calibration
- Calibration objective
- Synthetic/null world definition
- Injected edge definition, when applicable
- Dataset or generator reference
- Search/multiplicity configuration
- Sample sizes
- Seeds or deterministic generation controls
- Decision thresholds
- False-positive estimate
- False-negative estimate
- Power estimate
- Confidence intervals or uncertainty
- Representation variants
- Multiplicity variants
- Failure modes discovered
- Applicable scope
- Invalid scope
- Artifact paths and hashes
- Decision ID, when calibration is accepted or rejected
- Owner
- Created timestamp

A certifier is not considered calibrated merely because this schema exists. Empirical calibration evidence is required in M2.
