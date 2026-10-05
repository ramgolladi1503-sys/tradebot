# External Indian Market Data Source Corpus — 2026-08-27

## Purpose

Preserve the maximum defensible Indian-market data acquisition/recovery surface discovered from user-supplied GitHub links and their GitHub topic pages. This is a source corpus, not a declaration that advertised data has been recovered or accepted as authoritative.

Truth rule:

`SOURCE_DISCOVERED != DATA_RECOVERED != DATA_AUTHORITY_ACCEPTED`

Every source must be frozen at a commit, inspected, hash-bound where data exists, schema/timestamp/provenance audited, and independently classified before research use.

## Data-authority targets

- `DA-01` NIFTY futures + spot causal bars
- `DA-02` BANKNIFTY + SENSEX + NIFTYBEES + historical constituents
- `DA-03` volume + open interest
- `DA-04` India VIX and/or valid IV history
- `DA-05` expiry calendar + DTE history
- `DA-06` historical executable option bid/ask quotes
- `DA-07` survivorship + futures-roll metadata

---

## Priority sources

### SRC-01 — marketcalls/openchart

URL: `https://github.com/marketcalls/openchart`

Class: `OFFICIAL_DATA_ACQUISITION_ADAPTER`

Documented capabilities: NSE index/equity/F&O symbol search; historical OHLCV; 1m/5m/10m/15m/30m/1h/1d/1w/1M intervals; explicit `IDX`, `EQ`, `FO` segmentation; individual dated futures symbols; token/scripcode-aware access.

Potential value: very high for `DA-01`; high for linked-market bars in `DA-02`; volume but no documented historical OI for `DA-03`; investigate INDIA VIX for `DA-04`; partial expiry metadata for `DA-05`; no documented historical bid/ask for `DA-06`; high value for acquiring raw dated futures contracts for `DA-07`.

Required audit: prove expired-contract history depth, token identity, timestamp/bar semantics, raw-response provenance, coverage and applicable NSE terms before authority acceptance.

Disposition: `PRIORITY_EXTERNAL_ACQUISITION_CANDIDATE`

### SRC-02 — sajal101agrawal/nse-options-last-5-years

URL: `https://github.com/sajal101agrawal/nse-options-last-5-years`

Class: `BUNDLED_HISTORICAL_DERIVATIVES + PIPELINE`

README describes five years of NSE derivatives research data/pipeline, NSE Bhavcopy ingestion, Bhavcopies through Apr-2025 already included, Yahoo spot prices, FBIL rates, expiry handling, volume, computed IV/Greeks, JSON/PostgreSQL outputs.

Potential value: very high EOD candidate for `DA-03` if raw NSE Bhavcopy OI/volume fields are present; high candidate for `DA-05`; medium/high for raw dated futures-contract lineage in `DA-07`; derived IV only for `DA-04`; not historical executable bid/ask for `DA-06`; not an intraday `DA-01` solution.

Mandatory audit: inspect/hash `bhavcopy/raw` and `bhavcopy/extracted`, enumerate exact dates/fields, verify OI units, raw NSE provenance, licenses, and keep computed IV/Greeks separate from raw authority.

Disposition: `PRIORITY_BUNDLED_DATA_CANDIDATE`

### SRC-03 — ratan00/nse-rs

Discovered from `nse-option-chain` and `indian-stock-data` topic pages.

URL: `https://github.com/ratan00/nse-rs`

Class: `NSE_DATA_ACQUISITION_ADAPTER`

GitHub topic description states support for live equity quotes, futures, options, intraday charting candles and historical EOD Bhavcopy archives.

Potential value: high candidate for `DA-01`, `DA-02`, `DA-03`, `DA-05` and parts of `DA-07`; `DA-04` and `DA-06` require inspection.

Disposition: `PRIORITY_DISCOVERED_ADAPTER`

---

## Supporting historical / official-file acquisition sources

### SRC-04 — jugaad-py/jugaad-data
URL: `https://github.com/jugaad-py/jugaad-data`
Class: `HISTORICAL_NSE_DOWNLOAD_ADAPTER`
Role from GitHub topic pages: live/historical Indian market data and Bhavcopy downloading. Candidate for `DA-02`, `DA-05`, and cross-validation of official-file retrieval.

### SRC-05 — girishg4t/bhavCopy-downloader
URL: `https://github.com/girishg4t/bhavCopy-downloader`
Class: `EOD_OFFICIAL_FILE_DOWNLOADER`
Topic role: NSE/BSE bhavcopy including derivatives. Candidate for EOD `DA-03`, `DA-05`, and raw dated derivative contracts for `DA-07`.

### SRC-06 — BennyThadikaran/eod2 and BennyThadikaran/eod2_data
URLs: `https://github.com/BennyThadikaran/eod2`, `https://github.com/BennyThadikaran/eod2_data`
Class: `EOD_EQUITY_INDEX_HISTORY`
Role: NSE EOD historical stock/index/delivery download and companion historical CSV corpus. Useful supporting/cross-check source for `DA-02`; not an intraday futures authority.

### SRC-07 — NSEDownload/NSEDownload
URL: `https://github.com/NSEDownload/NSEDownload`
Class: `HISTORICAL_STOCK_INDEX_ADAPTER`
Role: historical NSE stocks/index data. Supporting `DA-02` cross-source verification.

### SRC-08 — debaonline4u/NSE-Data
URL: `https://github.com/debaonline4u/NSE-Data`
Class: `THIRD_PARTY_BUNDLED_INDEX_EQUITY_DATA`
Topic description: NIFTY 50/NIFTY Next 50 stock and index data in multiple timeframes. Authority requires provenance review; do not prefer over direct NSE-derived sources.

---

## Current/live option-chain and OI capture references

### SRC-09 — VarunS2002/Python-NSE-Option-Chain-Analyzer
URL: `https://github.com/VarunS2002/Python-NSE-Option-Chain-Analyzer`
Class: `CURRENT_OPTION_CHAIN_COLLECTOR / FIELD_SEMANTICS_SOURCE`
Role: near-real-time NSE option-chain retrieval and refresh. Useful for field semantics and future prospective OI/chain capture; not historical authority by itself.

### SRC-10 — manddar/Open-Interest-Data-Extractor
URL: `https://github.com/manddar/Open-Interest-Data-Extractor`
Class: `CURRENT_OI_ACQUISITION_REFERENCE`
Role: current NSE OI acquisition reference; not historical authority unless raw observations were persistently stored.

### SRC-11 — marketcalls/option-chain
URL: `https://github.com/marketcalls/option-chain`
Class: `CURRENT_OPTION_CHAIN_WEBSOCKET_MODULE`
Role: prospective option-chain capture architecture; not historical authority by itself.

### SRC-12 — broker option-chain connector references
Examples: `pramakrishn/express-option-chain`, `anurag-roy/kite-option-chain`, `anurag-roy/shoonya-option-chain`, `markov404/AngelOneOptionChainSmartApi`.
Class: `BROKER_OPTION_CHAIN_CONNECTOR_REFERENCE`
No broker acquisition, order, paper or live authority is granted by corpus inclusion.

---

## Derived analytics / methodology only

### SRC-13 — darshkale/nse-options-data-pipeline
URL: `https://github.com/darshkale/nse-options-data-pipeline`
Class: `REFERENCE_PIPELINE_NOT_FULL_DATASET`
README explicitly states full five-year production dataset is not included; demo uses synthetic sample data; IV/Greeks are computed; bid-ask/slippage are modeled. Useful for schema/transformation review only. It cannot satisfy `DA-06` historical bid/ask authority.

---

## Discovery roots

- `https://github.com/topics/nse-option-chain`
- `https://github.com/topics/indian-stock-data`
- `https://github.com/topics/nse-stock-data`

These are `DISCOVERY_ROOT_ONLY`; topic membership is not data authority.

---

## Existing internal TradeBot data to join into the same authority graph

Repository evidence also identifies a partial historical NIFTY futures acquisition:

- instrument identity: `NSE_FO|61093`
- `NIFTY FUT 28 JUL 26`
- 18,375 rows
- 49 sessions
- approximately 2026-05-12 through 2026-07-21
- original research contract marks it partial / DEV-only

Class: `INTERNAL_PARTIAL_FUTURES_AUTHORITY`

It is valuable for explicit futures identity but its original evidence limitations must not be silently expanded.

---

## Maximum-data architecture

Do not combine everything into one opaque CSV.

### R0 — immutable raw provenance
Preserve raw NSE Bhavcopy ZIPs, raw historical API responses, instrument masters, raw option-chain JSON, individual futures bars, index/equity bars, VIX data when recovered, and historical quote/depth captures when recovered. Every object gets source, SHA256, instrument identity, acquisition/request metadata, and legal/licensing note.

### R1 — normalized authoritative tables
Canonical logical tables: `index_bars`, `futures_bars`, `option_eod`, `option_chain_snapshots`, `constituent_membership`, `expiry_calendar`, `india_vix`, `instrument_master`.

### R2 — deterministic derived research tables
Examples: continuous futures, DTE, basis, breadth, dispersion, realized volatility, path efficiency, derived IV/Greeks. Every derived row lineage must terminate in accepted R0/R1 sources and versioned transformation code.

---

## Current coverage view

| Source | DA-01 | DA-02 | DA-03 | DA-04 | DA-05 | DA-06 | DA-07 |
|---|---|---|---|---|---|---|---|
| OpenChart | HIGH candidate | HIGH | Volume | investigate VIX | partial | no evidence | HIGH raw contracts |
| Sajal 5y repo | EOD only | partial | HIGH EOD OI/volume candidate | derived IV | HIGH candidate | NO bid/ask | MEDIUM/HIGH |
| nse-rs | HIGH candidate | HIGH candidate | HIGH candidate | investigate | HIGH candidate | unknown | MEDIUM/HIGH |
| jugaad-data | partial | HIGH EOD | possible Bhavcopy | unknown | medium | no evidence | medium |
| bhavCopy-downloader | EOD | low | HIGH EOD candidate | no | HIGH candidate | no | medium |
| eod2/eod2_data | no futures | HIGH EOD | limited | no | low | no | constituent support |
| Varun analyzer | current only | current context | current OI | current/derived | current expiries | unknown | no |
| Darsh pipeline | no new authority | no | processes OI | derived IV | derived | MODELED ONLY | no |
| internal identified FUT | HIGH but partial | no | audit volume | no | contract expiry known | no | one contract only |

---

## Acquisition priority

1. `DA-01`: OpenChart + nse-rs + internal identified futures corpus to prove spot/futures intraday identity.
2. `DA-03/DA-05`: inspect Sajal raw Bhavcopy bundle; independently reproduce with bhavCopy-downloader/jugaad-data/nse-rs.
3. `DA-02`: OpenChart/nse-rs plus EOD sources and existing TradeBot constituent panels.
4. `DA-04`: probe INDIA VIX through direct NSE-derived adapters; keep India VIX distinct from computed option IV.
5. Prospective option-chain/OI capture: use current collectors only under separate governed read-only acquisition authority.
6. `DA-06`: remains unresolved. None of the supplied sources currently proves a historical executable bid/ask archive. Never substitute Bhavcopy, LTP, modeled spreads or synthetic samples.

---

## Ingestion contract

For every admitted source:
1. freeze repository URL/branch/commit;
2. preserve README/license;
3. classify source as bundled data, acquisition adapter, live collector, derived pipeline or discovery root;
4. inventory actual data separately from code;
5. hash raw data;
6. record schema/coverage;
7. verify provenance/timestamp semantics/instrument identity;
8. record licensing constraints;
9. select authority before seeing strategy performance;
10. cross-check overlapping data from independent sources where possible.

Allowed authority verdicts:
`AUTHORITATIVE_ACCEPTED`, `AUTHORITATIVE_ACCEPTED_WITH_LIMITATIONS`, `DERIVED_ACCEPTED`, `PARTIAL_COVERAGE_ONLY`, `PROVENANCE_INSUFFICIENT`, `TIMESTAMP_SEMANTICS_UNRESOLVED`, `IDENTITY_UNRESOLVED`, `QUALITY_FAILURE`, `NOT_FOUND`.

## Explicit non-claims

`SOURCE_CORPUS_BUILT=true`
`ALL_SOURCE_DATA_DOWNLOADED=false`
`ALL_SOURCE_DATA_AUTHORITATIVE=false`
`DA06_HISTORICAL_BIDASK_RECOVERED=false`
`HYPOTHESIS_VALIDATION_RUN=false`
`STRUCTURAL_EDGE_CERTIFIED=false`
