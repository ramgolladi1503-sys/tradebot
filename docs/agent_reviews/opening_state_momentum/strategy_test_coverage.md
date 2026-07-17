# Strategy Test Coverage Evidence

This file provides proof of the test coverage for the semantic behavior of the strategy.

## Pytest Output for Collection Only
```text
$(cat pytest_collect.txt)
```

## Pytest Output for All Tests
```text
$(cat pytest_all.txt)
```

## Pytest Output for Specific Keywords
```text
$(cat pytest_k.txt)
```

## Test Mappings
- `test_exact_instrument_classification`: Proves exact instrument classification (NIFTY, BANKNIFTY vs SENSEX, REJECT).
- `test_time_boundaries`: Proves timestamp conditions (14:45 cutoff, 14:46 entry).
- `test_causality_and_mutation`: Proves feature invariance to later candle mutations.
- `test_holdout_date_formats`: Proves holdout lock for string, date, and timestamp formats.
- `test_direct_single_session_holdout`, `test_batch_only_holdout`, `test_mixed_batch`: Prove `HOLDOUT_LOCKED` exception for outcome evaluation.
