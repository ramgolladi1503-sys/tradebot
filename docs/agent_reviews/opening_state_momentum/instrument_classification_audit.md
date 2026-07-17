# Instrument Classification Audit

The candidate replay logic uses exact parsed identities based on the filename stem and the extracted date. It does not use substring tests, preventing ambiguity or mismatch.

Test coverage in `test_strategy.py::test_exact_instrument_classification` proves:
```text
NIFTY_20250709.parquet       -> NIFTY
BANKNIFTY_20250709.parquet   -> BANKNIFTY
SENSEX_20250709.parquet      -> SENSEX
MYNIFTY_20250709.parquet     -> REJECT
BANKNIFTYX_20250709.parquet  -> REJECT
NIFTY_BANKNIFTY.parquet      -> REJECT_AMBIGUOUS
```
