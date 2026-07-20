# ORB Parameter Ownership Matrix

| Parameter | Value | Runtime Role | Impact |
| --- | ---: | --- | --- |
| MIN_RETEST_MINUTES | 15 | REQUIRED_BUT_INERT | Profile claims a retest-minute bound that cannot affect emitted candidates. |
| MAX_RETEST_MINUTES | 90 | REQUIRED_BUT_INERT | Profile claims a retest-minute bound that cannot affect emitted candidates. |
| MAX_RETEST_DISTANCE_PCT | 0.0018 | SCORE_ONLY | Changes raw score but not candidate inclusion. |
| MIN_BREAKOUT_DISTANCE_PCT | 0.0008 | SCORE_ONLY | Changes raw score but not candidate inclusion. |
| OPENING_RANGE_BARS | 15 | HARD_CODED_TEMPORAL_GATE | Controls opening-range completion independently of profile. |
| MAX_BREAKOUT_TO_RETEST_AGE | 5 | HARD_CODED_TEMPORAL_GATE | Controls breakout-to-retest max age independently of profile. |
| MAX_RETEST_TO_CONTINUATION_AGE | 3 | HARD_CODED_TEMPORAL_GATE | Controls retest-to-continuation max age independently of profile. |
| BREAKOUT_SCORE_FULL_SATURATION | 0.004 | UNOWNED_SCORE_CONSTANT | Affects ranking score without profile ownership. |
