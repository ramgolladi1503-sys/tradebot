# Option E2E Contract Reconstruction v4.1

## Verdict

PARTIALLY PROVEN for observed quote-file tokens only. NOT PROVEN for historical contract existence.

The local corpus contains contemporaneous quote/depth rows with immutable file hashes and quote values, and 1,262 of the 1,325 census-known quote files can be joined to NIFTY CE/PE strike/expiry identity through `runtime/upstox_instruments/complete.json`. That join is not a point-in-time authority: it is a current local Upstox instrument snapshot with no capture timestamp, no provider manifest timestamp, and no proof it was valid when the quote rows were captured. Therefore these files do not prove observed historical contract existence under the requested standard.

Safety flags: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`, `append=false`.

## Scope

- Worktree: `/Users/madhuram/tradebot-option-e2e-contract-reconstruction-v4`
- Branch: `research/option-e2e-contract-reconstruction-v4`
- Starting commit: `c0a3498424744b623257845068528ccf528396df`
- Owned paths:
  - `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/**`
  - `docs/agent_reviews/option_e2e_contract_reconstruction_v4_1.md`
  - `tests/research/option_e2e/test_contract_reconstruction_v4_1.py`
- Not touched: shared resolver code, broker code, live runtime, strategy code, risk/feed gates, credentials, config.

## Coverage Matrix

Artifacts:

- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.csv`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/summary.json`
- `research/option_e2e_recertification_v4/contract_reconstruction_v4_1/coverage_matrix.json.sha256`

Summary:

| Metric | Count |
| --- | ---: |
| Census-known quote files evaluated | 1,325 |
| Newly discoverable local candidates evaluated | 11 |
| Total discovered quote/depth-like files | 1,336 |
| Files classified as quote-like | 1,327 |
| Files classified as depth-like | 1 |
| Files with reconstructed NIFTY option identity | 1,264 |
| Census-known files with reconstructed NIFTY option identity | 1,262 |
| Files proving historical contract existence | 0 |
| Files blocked by missing point-in-time authority | 1,336 |

Required proof fields:

| Requirement | Coverage | Verdict |
| --- | ---: | --- |
| Timestamp | Most quote/depth files include `ts`, `exchange_timestamp`, or sample `timestamp` | PARTIALLY PROVEN |
| Symbol/token | Quote files include `instrument_key`; depth file includes `symbol` and `instrument_token` | PARTIALLY PROVEN |
| NIFTY | Reconstructed for 1,264 files via current Upstox master, or present as symbol in the depth file | PARTIALLY PROVEN |
| CE/PE | Reconstructed for 1,264 files via current Upstox master | PARTIALLY PROVEN |
| Strike | Reconstructed for 1,264 files via current Upstox master | PARTIALLY PROVEN |
| Expiry | Reconstructed for 1,264 files via current Upstox master | PARTIALLY PROVEN |
| Provider/source identity | 1,323 paths are under Upstox runtime roots; 13 are unknown/local examples or manifests | PARTIALLY PROVEN |
| Immutable file hash | SHA256 recorded for every discovered file | PROVEN |
| Quote values | Quote-like rows expose LTP/bid/ask or OHLC-style quote fields | PARTIALLY PROVEN |
| Depth values | `runtime/strategy_validation/resolved_option_ticks_20260702.parquet` has `best_bid`, `best_ask`, and `depth_json` | PROVEN FOR DEPTH FILE ONLY |
| No post-expiry rows | Can be checked only after identity reconstruction; not authoritative without point-in-time expiry source | PARTIALLY PROVEN |
| Historical contract existence | Requires all fields plus point-in-time authority | NOT PROVEN |

## Blockers

Primary blocker: `NO_POINT_IN_TIME_INSTRUMENT_AUTHORITY` for all 1,336 files.

Why this matters: the quote files show observed tokens at quote timestamps, but tokens alone do not prove that the token mapped to a specific NIFTY CE/PE strike/expiry at that historical time. The only local mapping source used here is `runtime/upstox_instruments/complete.json`, which is a current snapshot. Using it as historical truth would be survivorship-prone and can silently misclassify expired, reused, corrected, or changed instruments.

Additional blockers:

- `NO_NIFTY_CE_PE_TOKEN_MATCH`: 72 files/candidates did not reconstruct to a NIFTY CE/PE token.
- `NO_POST_EXPIRY_PROOF_UNAVAILABLE_OR_FAILED`: 74 files/candidates could not prove no post-expiry rows.
- `READ_FAILED:EmptyDataError`: 4 empty external manifest CSV candidates were hashed and blocked, not ignored.

## Representative Hashes

- Coverage matrix JSON: `1541c8017b18265c3db03716a01de61eca8e406689b148daabe11b5bbf92eb86`
- Coverage payload hash: `120c91acc412557c88baa1d8183275be8b25f080b4b6efdf28002c59901172a7`
- Analyzer source: `080e0aa07a4598ad0d0453cc462b82306974c541e409211257ae34190e70e17b`
- Depth candidate `runtime/strategy_validation/resolved_option_ticks_20260702.parquet`: `7ef6dfae7de94a1f52fac97b007259ada769347ff72299e238b6cac43ab54508`
- Example quote candidate `runtime/market_data/upstox/20260713/ticks_1783918406.parquet`: recorded in `coverage_matrix.json`; matrix hash above binds the row and file hash.

## Tests

Command:

```bash
pytest -q tests/research/option_e2e/test_contract_reconstruction_v4_1.py
```

Result:

```text
2 passed
```

The tests prove:

- NIFTY CE/PE identity can be reconstructed from a local Upstox master and quote token.
- The reconstruction still fails closed when the master is not point-in-time authority.
- Artifact writing emits a hash file for the matrix.

## Run Instructions

```bash
python -m research.option_e2e_recertification_v4.contract_reconstruction_v4_1.analyze_contract_reconstruction
pytest -q tests/research/option_e2e/test_contract_reconstruction_v4_1.py
```

## Migration Notes

No runtime migration. No config keys added. No production wiring.

To upgrade this from PARTIALLY PROVEN to PROVEN, add a dated, immutable provider instrument master or contract-chain snapshot captured at or before each quote file timestamp, with its own SHA256 and provider/capture manifest. Do not promote current `complete.json` to historical authority without that provenance.
