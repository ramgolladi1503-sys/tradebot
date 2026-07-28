# PR709 V2 versus V3 Comparison

V2: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v2`
V3: `/Users/madhuram/tradebot-ml-evidence/constituent-lead-lag-data-v1/proxy_campaign_2024_2025_v3`

## Key Differences

- completed_regular_sessions: v2=`None` v3=`409`
- theoretical_max_state_rows: v2=`4110` v3=`4090`
- state_rows: v2=`4110` v3=`4090`
- unweighted_state_rows: v2=`None` v3=`4090`
- weighted_signals: v2=`0` v3=`0`
- unweighted_signals: v2=`1` v3=`1`
- proxy_final_decision: v2=`None` v3=`NO_QUALIFYING_SIGNALS_UNDER_VALID_PROXY_CONTRACT`

## Oracle
- v2 oracle verdict: `PASS`
- v3 oracle verdict: `PASS`

## Attribution
Differences are attributed to v3 certification-contract changes unless source strategy thresholds changed; thresholds were not tuned.
