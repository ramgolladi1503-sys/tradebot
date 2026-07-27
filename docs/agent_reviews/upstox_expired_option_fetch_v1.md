# Upstox Expired Option Fetch V1

## Execution Scope
- Worktree: `/Users/madhuram/tradebot-upstox-expired-option-fetch-v1`
- Branch: `data/upstox-expired-option-fetch-v1`
- Evidence Root: `/Users/madhuram/tradebot-ml-evidence/upstox-expired-options-v1`

## Validation Results
- Data Quality: Validated (no OHLC violations detected in complete bars)
- Determinism Proof: `FIXTURE_NORMALIZATION_DETERMINISM_PASS_WITH_FULL_DATASET_SEMANTIC_INVENTORY` (15-file fixture scope for normalization determinism; full 1199-file scope for semantic dataset hashing)
- Resume/Idempotence Proof: `FIXTURE_FILESYSTEM_RESUME_PASS` (15-file filesystem-based simulation)
- Security Audit: PASS (No tokens leaked)
  - Credential Revocation: `USER_CONFIRMATION_NOT_AVAILABLE`
- Reconciliation: PASS (1199 populated raw aligned perfectly with 1199 normalized)
- Full Dataset Semantic Inventory: `FULL_DATASET_SEMANTIC_INVENTORY_PASS` (0 mismatches across 1199 files run independently twice)

## Historic Invalidation
- The previous hash `44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a` is EXPLICITLY INVALIDATED. It was an empty object hash `{}` caused by an os.listdir root traversal defect.
- The defect has been repaired with a canonical semantic hashing implementation (`semantic_hash.py`) and accurate deep path traversal (`rglob`).

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
