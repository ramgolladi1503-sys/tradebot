# Results

## Verdict

```text
DATA_BLOCKED_INSUFFICIENT_SESSIONS_AND_MISSING_UNDERLYING_VOLUME_AND_MISSING_CONSTITUENTS
```

## Blocking gates

```text
INSUFFICIENT_INDEPENDENT_COMPLETE_SESSIONS_1_LT_30
MISSING_CAUSAL_NIFTY_UNDERLYING_VOLUME
MISSING_NIFTY_CONSTITUENT_PARTICIPATION
```

## What passed

- raw-source and extract SHA-256 lineage recorded;
- timestamp normalization to Asia/Kolkata;
- completed five-minute NIFTY bar construction;
- prior-completed-HTF level mapping;
- frozen Gravity-Well family implementation;
- strict refusal to treat tick count as volume;
- strict refusal to manufacture constituent breadth;
- observed NIFTY option-symbol parsing for spaced and compact formats;
- next-bar option timing and bid/ask truth controls;
- exact-ATM versus nearest-strike identity separation;
- focused causal tests: `9 passed`.

## What did not run

The following were not opened because the data-authority gate failed:

- primary family event evaluation;
- normal-day versus expiry-day comparison;
- baseline and existing-MEG incremental uplift;
- chronological development/validation/holdout evaluation;
- bootstrap confidence intervals;
- neighbouring-parameter robustness;
- winner-removal and concentration controls;
- structural-edge certification.

## Diagnostic-only output

| Control | Side | Events |
|---|---:|---:|
| Price-only escape | Long | 6 |
| Price-only escape | Short | 4 |
| Price-only failed escape | Long | 1 |
| Price-only failed escape | Short | 3 |
| Location-only cluster break | Long | 2 |
| Location-only cluster break | Short | 1 |

One exact-ATM diagnostic option trade was available and returned `-5.3005%` after primary friction. This is plumbing evidence only; it is not a strategy result.

## Decision

Do not integrate Gravity Well as a TradeBot strategy. Do not optimize thresholds against these sessions. Acquire or recover the missing multi-session constituent corpus, then rerun the frozen specification unchanged.
