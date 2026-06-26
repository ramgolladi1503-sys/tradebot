# Regime Entropy Truth Contract & Prod-Grade Fixes Report

## Files Changed
- `config/config.py`: Added session-aware normalized entropy thresholds and missing timing SLAs (`LIVE_OPTION_LTP_MAX_AGE_SEC` etc).
- `core/entropy_contract.py`: Created central math module ensuring mathematically valid regime distributions, exposing `shannon_entropy` and `normalized_entropy`.
- `core/data_quality.py`: Created central `DataQualityState` schema for truth separation.
- `core/regime_prob_model.py`: Rewired regime prediction to use normalized entropy and session thresholds instead of a generic `1.3` threshold.
- `core/candidate_scoring.py`: Fixed the neutral-default bugs so `LIVE` missing quotes block scoring entirely instead of reverting to `0.5`. Aligned timing scores with the strict `LIVE` vs `PAPER` SLAs. Disabled `RR_FALLBACK` for `LIVE` execution modes.
- `core/candidate_ranking.py`: Refactored feed risk parsing to use a new `is_feed_risk_candidate` quarantine gate. Feed-risk candidates like `FALLBACK` data are now forcefully degraded to `SUPPRESSED` and prevented from entering Top Opportunities.
- `dashboard/streamlit_app_runtime.py`: Split the Streamlit output to explicitly show `Top Opportunities`, `Watchlist / Near Executable`, `Advisory / Debug Candidates`, and `Suppressed Candidates`.

## Bugs Found & Old Behavior
- **Entropy Math Mixing**: Entropy max was hardcoded to `1.3`, which fails to contextualize `ln(N)` states where N is the number of regimes (e.g., `ln(5) = 1.609`). Entropy of `1.399` was flagged as globally broken/impossible when it was mathematically plausible.
- **Fake Default Scores**: Missing spread, timing, or liquidity metrics during a LIVE run artificially generated average `.5` scores, masking data outages as valid trading opportunities.
- **Fallback Leakage**: `FALLBACK` or recovered quote data could seep into `Top Opportunities` and get recommended as the primary actionable trade if everything else was bad.

## Exact New Behavior
- Entropy evaluations strictly validate arrays sum to 1.0. Calculations return mathematically sound normalized values within `[0.0, 1.0]`. 
- `LIVE` missing quotes and lack of Risk-Reward bounds are tagged with `live_block` penalization and drop scoring to zero instead of creating median fake scores.
- Candidates with missing execution properties or untrusted sources will never reach `EXECUTABLE` state; they are safely swept into the newly created `Advisory` or `Suppressed` sections of the dashboard.
- If all clean candidates are missing/degraded, the system suppresses action and flags `NO_TRADE`.

## Entropy Formula Used
- **Shannon Entropy**: `- \sum P(x) * \ln(P(x))`
- **Max Entropy**: `\ln(N)` where `N=5` (for five standard Regimes) translates to `~1.609`. 
- An entropy of `1.399` divided by `1.609` evaluates to `~0.869`, which represents high market uncertainty but is logically valid under the unified thresholds.

## Evidence From Tests
- Passed tests confirming: 
    - One-hot distributions equal exactly zero entropy.
    - Uniform `5`-regime distributions generate mathematically exact `ln(5)` max_entropy bounds.
    - Invalid floating-point distributions naturally fail and abort.

## Recommended Next PRs
1. Train/calibrate regime probability model from historical NIFTY/BANKNIFTY/SENSEX data.
2. Add replay-based entropy distribution report by session bucket.
3. Add strategy-regime compatibility matrix.
4. Add calibrated outcome probability contract for target-hit probability.
5. Add live paper validation comparing Top Opportunities vs future option traces.
