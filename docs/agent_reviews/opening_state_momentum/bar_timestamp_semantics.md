# Bar Timestamp Semantics Evidence

Upstox one-minute timestamps represent candle-open times. The 14:44:00 candle covers trading activity from 14:44:00 to 14:44:59, closing at 14:45:00.

## Frozen Time Boundaries
- decision time: 14:45:00 Asia/Kolkata
- last legal feature-bar open: 14:44:00
- last legal feature-bar completion: 14:45:00
- earliest legal entry-bar open: 14:45:00

The tests in `test_strategy.py::test_causality_and_mutation` rigorously enforce this causality boundary. Mutations at 14:45:00 or later do not alter the candidate decision, ensuring no future knowledge leaks into feature computation.
