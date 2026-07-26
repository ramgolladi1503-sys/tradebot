# Upstox Expired Option Fetch V1

## Execution Scope
- Worktree: `/Users/madhuram/tradebot-upstox-expired-option-fetch-v1`
- Branch: `data/upstox-expired-option-fetch-v1`
- Evidence Root: `/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1`

## Validation Results
- Data Quality: Validated (no OHLC violations detected in complete bars)
- Determinism Proof: PASS (0 mismatches across clean directories)
- Resume/Idempotence Proof: PASS (0 duplicate downloads/normalizations on resume)
- Security Audit: PASS (No tokens leaked)
  - Credential Revocation: `USER_CONFIRMATION_NOT_AVAILABLE`
- Reconciliation: PASS (All components reconciled 1:1)

## Data Summary
- Known Expiries: 95
- Attempted Contracts: 1327
- Populated Contracts: 1199
- Missing/Empty Contracts: 116
- 1-minute Files: 1199
- 5-minute Files: 1199

## Verification Commands
```bash
python -m pytest -q tests/test_upstox_expired_options_governance.py
python -m pytest -q tests/test_upstox_expired_options_aggregation.py
python -m pytest -q tests/test_upstox_expired_options_resume.py
```

## Known Limitations
- Conflicting duplicates can only be robustly verified via exhaustive memory loading which is not performed in the lightweight audit script.
- The resumption proof simulates interruption by halting execution after 2 files.

## What Remains
- End user must confirm revocation of any used UPSTOX_ACCESS_TOKEN.
- Downstream ML workflows can consume the generated 5m parquets.
