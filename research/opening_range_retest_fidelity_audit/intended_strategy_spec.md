# Opening Range Retest Intended Strategy Spec

Read-only audit artifact. No production code, broker path, or execution path is changed.

## Implemented Sequence
- first 15 complete 1m bars define OR high and OR low
- breakout bar closes beyond OR boundary
- later retest touches boundary and closes on breakout side
- later continuation closes beyond retest bar extreme
- candidate emits only when continuation is the latest completed bar

## Not Implemented As Candidate Gates
- MIN_RETEST_MINUTES
- MAX_RETEST_MINUTES
- MAX_RETEST_DISTANCE_PCT
- MIN_BREAKOUT_DISTANCE_PCT
- VWAP alignment
