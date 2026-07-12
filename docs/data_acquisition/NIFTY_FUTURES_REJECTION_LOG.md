# NIFTY Futures Rejection Log

## Official NSE Sources
*   **NSE Contract-wise Data:** Rejected because the web interface requires manual form submission and is protected by aggressive anti-bot (Cloudflare) measures, preventing automated download without bypassing restrictions. Data is also often limited to daily summaries.
*   **NSE Archives:** Rejected due to aggressive anti-bot protection and zip structures that require interactive navigation.

## Third-Party Data Vendors
*   **TrueData / Global Datafeeds:** Rejected because these are paid commercial APIs requiring subscription and authentication, violating the requirement for a public, freely accessible dataset without credential bypass.
*   **Investing.com:** Rejected because the exported data is limited to daily granularity, and the terms of service prohibit automated scraping.

## GitHub Repositories
*   **abhinavitgithub/Financial-analysis-and-visualisation:** Rejected. The file `Nifty 50 Futures Historical Data.csv` has only daily granularity.
*   **sandeepkapri/Nifty50-Minute-Data:** Rejected. Contains 1-minute OHLC data but for the NIFTY Spot index. It has no volume column.
*   **Me-Avinash/python-tvdatafeed-historical-downloader:** Rejected. This is a script that requires TradingView login credentials to scrape data.
*   **Paratyaksh03/Stock-Predictor-LSTM:** Rejected. Unknown instrument, lacks documentation on the data source.
*   **BobiRaj/Bank-Nifty-Intraday-Historical-data:** Rejected. Contains Bank Nifty data, not Nifty 50.
*   **ayushnaithaniii-collab/Nifty-iv-event-study:** Rejected. Focuses on Options and Implied Volatility, not futures volume.
*   **vishalvx/nifty-indices-datasets:** Rejected. Contains index constituents, not trading data.
*   **lamba-manish/nifty_indices_and_usdinr_prediction:** Rejected. Contains spot index data only.
*   **theayushgupta08/nifty-indices-web-scrapping:** Rejected. Scrapes spot index data from NiftyIndices.
*   **laxmikanth-gh/nifty-indices-investment-analysis:** Rejected. Uses spot index data.
*   **kathyayini-25/15-BankNifty-Index-Price-Forecasting-using-LSTM-and-ARIMA:** Rejected. Focuses on Bank Nifty.
*   **akshit-iitbm/SOC_AlgorithmicIntradayTrading:** Rejected. Repository contains only code, no historical datasets.

## Kaggle & Zenodo
*   **Kaggle Nifty 50 Futures / NSE Minute Data:** Rejected. Downloading from Kaggle via script requires a Kaggle API key (authentication bypass), and datasets are behind a login wall.
*   **Zenodo Nifty Datasets:** Rejected. No relevant NIFTY futures datasets found via search.
