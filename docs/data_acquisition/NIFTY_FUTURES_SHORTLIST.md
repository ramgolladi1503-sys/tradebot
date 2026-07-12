# NIFTY Futures Source Shortlist

## 1. abhinavitgithub/Financial-analysis-and-visualisation
*   **Reason for shortlisting:** Appeared to contain historical data specifically labeled "Nifty 50 Futures" in a CSV file format, downloadable without authentication.
*   **Result after download:** Rejected. The data was found to be daily granularity, which violates the minimum requirement of 1-minute OHLCV data.

## 2. sandeepkapri/Nifty50-Minute-Data
*   **Reason for shortlisting:** Contained 1-minute OHLC data for NIFTY over a multi-year period, which is exactly the granularity required, and was freely downloadable.
*   **Result after download:** Rejected. The data represents the NIFTY Spot index, not futures. It completely lacks any volume column.

## Conclusion
No viable short-listed candidates successfully passed the initial inspection for both correct instrument identity (NIFTY Futures) and correct granularity (1-minute or better with volume).
