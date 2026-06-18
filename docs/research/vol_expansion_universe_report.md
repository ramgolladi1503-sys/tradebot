# VOL_EXPANSION Universe Research Report

## Mission Objective
Determine whether `HTF_RANGE_EXPANSION` is the *best* implementation of the Volatility Expansion edge, or merely the *first* discovered. To answer this, we isolated all mathematical volatility states to map the raw physical opportunity unadulterated by any strategy gates.

## Findings: What exactly is the edge?
The edge of `VOL_EXPANSION` is **not** a raw, persistent directional drift that can be blindly exploited by simple breakouts. The baseline naivety test across all subtypes yielded universally negative net expectancies (Opportunity Scores ranging from -2.5 to -18.1).

The edge is explicitly **conditional and structural**. `HTF_RANGE_EXPANSION` produces a positive expectancy (+0.47R) not because it rides an inherent volatility wave, but because it employs ruthless structural gating (e.g. 15m/30m alignment, VWAP compression checks, and opening drive thresholds) to filter out the noise.

## When does it appear?
- **Trend Continuation Expansions**: These represent the vast majority of mathematical opportunities (51 instances), exhibiting strong MFE (1.22R). The edge appears most visibly when the intraday volatility directly aligns with the broader structural path.
- **Opening Expansions**: The second most frequent (38 instances), generating the highest isolated MFE (1.41R). The edge manifests forcefully in the first hour when institutional positioning cascades.

## When does it disappear?
- **Gap Expansions**: When the market opens with a massive gap (> 0.5%), the structural expansion edge completely disintegrates. The baseline expectancy plummets to -1.08R (the worst of all subtypes) and the Profit Factor drops to a catastrophic 0.08.

## Subtype Valuations
### Which expansion subtype is most valuable?
**Opening Expansions** combined with **Trend Continuation** provide the highest ceiling of raw uncaptured edge (Highest MFE profiles). `HTF_RANGE_EXPANSION` inherently exploits this by locking its entries to the opening structural ranges.

### Which expansion subtype should never be traded?
**Gap Expansions**. The data unequivocally proves that massive gap-ups/downs inside a high-volatility regime drain all subsequent intraday mathematical edge. The initial gap consumes the entirety of the expansion vector, leaving nothing but chopped friction for intraday participants.

## Final Verdict
`HTF_RANGE_EXPANSION` is **not merely the first implementation, it is currently the mathematically optimal implementation**. By natively avoiding pure naive breakouts and heavily gating its executions against structural exhaustion, it successfully extracts the only slivers of positive expectancy from what is otherwise a mathematically net-negative raw environment.
