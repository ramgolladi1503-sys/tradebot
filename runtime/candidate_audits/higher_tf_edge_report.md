# Higher-Timeframe Edge Pivot Report (Proxy Analysis)

We evaluated HTF structural entries across 3 distinct execution proxies to perfectly isolate signal quality from transaction costs.

## Proxy Comparison Matrix (Net R)
| strategy                     |   ATM_OPTION_PROXY |   FUTURES_PROXY |   ITM_OPTION_PROXY |
|:-----------------------------|-------------------:|----------------:|-------------------:|
| HTF_15M_TREND_CONT           |         -0.0731242 |       -0.176846 |         -0.0461682 |
| HTF_FAILED_BREAKOUT_REVERSAL |         -0.0487368 |       -0.181287 |         -0.0139235 |
| HTF_OPENING_DRIVE_CONT       |         -0.0166064 |       -0.166214 |          0.0217527 |
| HTF_PDH_PDL_HOLD             |         -0.111388  |       -0.282187 |         -0.0675723 |
| HTF_RANGE_EXPANSION          |          0.504796  |        0.38578  |          0.535043  |

## Conclusion
A candidate must first show edge under FUTURES_PROXY to be considered. Then, ITM/ATM proxies demonstrate how much slippage and taxes erode that base edge.
