# HTF Signal Starvation RCA Report

This diagnostic report traces exactly where HTF strategies are choked in the gating funnel.

## Signal Decay Funnel
| strategy                     |   raw_setup_count |   rejected_by_session |   rejected_by_15m_regime |   rejected_by_30m_regime |   rejected_by_volatility |   rejected_by_vwap_cond |   rejected_by_pdh_pdl |   rejected_by_structure |   rejected_by_execution_availability |   final_trades |
|:-----------------------------|------------------:|----------------------:|-------------------------:|-------------------------:|-------------------------:|------------------------:|----------------------:|------------------------:|-------------------------------------:|---------------:|
| HTF_15M_TREND_CONT           |             11764 |                  2962 |                     1361 |                     2830 |                        0 |                       0 |                     0 |                    3441 |                                    0 |           1170 |
| HTF_15M_VWAP_PULLBACK        |             11764 |                  2962 |                     1361 |                     2830 |                        0 |                    4611 |                     0 |                       0 |                                    0 |              0 |
| HTF_OPENING_DRIVE_CONT       |             11764 |                  2962 |                     1361 |                     2830 |                        0 |                       0 |                     0 |                    1932 |                                    0 |           2679 |
| HTF_PDH_PDL_HOLD             |             11764 |                  2962 |                        0 |                        0 |                        0 |                       0 |                  4405 |                       0 |                                    0 |           4397 |
| HTF_FAILED_BREAKOUT_REVERSAL |             11764 |                  2962 |                     4611 |                        0 |                        0 |                       0 |                     0 |                    3416 |                                    0 |            775 |
| HTF_RANGE_EXPANSION          |             11764 |                  2962 |                        0 |                        0 |                     7758 |                       0 |                     0 |                     317 |                                    0 |            727 |

## Gate Ablation Matrix
Observe how trade counts scale as gates are incrementally relaxed or bypassed.

| strategy                     |   Baseline |   15m regime only |   30m regime only |   15m OR 30m regime |   no regime, structure only |   regime only, no structure |   structure + session only |
|:-----------------------------|-----------:|------------------:|------------------:|--------------------:|----------------------------:|----------------------------:|---------------------------:|
| HTF_15M_TREND_CONT           |       1170 |              1607 |              1321 |                1767 |                        1686 |                        5446 |                       1686 |
| HTF_15M_VWAP_PULLBACK        |          0 |                 0 |                 0 |                   0 |                           0 |                        5446 |                          0 |
| HTF_OPENING_DRIVE_CONT       |       2679 |              3129 |              2795 |                3561 |                        4396 |                        5446 |                       4396 |
| HTF_PDH_PDL_HOLD             |       4397 |              4397 |              4397 |                4397 |                        4397 |                        5446 |                       4397 |
| HTF_FAILED_BREAKOUT_REVERSAL |        775 |               775 |               775 |                 775 |                        1291 |                        5446 |                       1291 |
| HTF_RANGE_EXPANSION          |        727 |               727 |               727 |                 727 |                        4396 |                        5446 |                       4396 |

## Root Cause Assessment
By mapping the ablation matrix, we identify the exact structural chokehold per variant. No optimizations are derived from this—only diagnostic mapping.
