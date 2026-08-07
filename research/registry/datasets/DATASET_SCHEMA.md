# Dataset Registry Schema

Each dataset record must contain:

- Dataset ID
- Version
- Name and description
- Provider/source
- Acquisition method
- License or usage constraints
- Asset/instrument universe
- Market/timezone/calendar
- Coverage start and end
- Native frequency and timestamp semantics
- Fields and units
- Corporate-action / contract-roll handling where applicable
- Missingness and gap policy
- Duplicate policy
- Survivorship and constituent-selection treatment
- Symbol/instrument mapping rules
- Raw artifact locations and hashes
- Transformation lineage
- Derived-from Dataset IDs
- Integrity checks and results
- Known defects and exclusions
- Data authority status
- Owner
- Acquisition timestamp
- Last validation timestamp

Derived datasets require their own Dataset IDs when transformations materially affect scientific interpretation or reproducibility.
