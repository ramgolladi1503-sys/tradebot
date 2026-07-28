# trend_pullback_v1

Verdict: `TREND_PULLBACK_STRATEGY_INTENT_AMBIGUOUS`

Actual thesis: Production gates on TREND_UP/TREND_DOWN score and spot proximity/resume distance versus nearest support/resistance fallback to VWAP; no trend duration, impulse magnitude, pullback history, or structure-break sequence is represented in the strategy file.

Reachability: The score gates are theoretically reachable from MovementRegimeClassifier, but exact production-context historical truth remains blocked/missing from prior readiness gate.

Objective defects: 0

Design ambiguities:
- Trend-establishment equation, minimum duration, impulse magnitude, support/resistance owner, and continuation trigger are not defined by available Level-1 artifacts; named provenance files are absent.
