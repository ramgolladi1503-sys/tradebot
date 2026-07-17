# Case study: structural MVP ceiling

The JSONL fixture is intentionally small and deterministic. It proves orchestration, actual callable invocation, evidence persistence, WFA routing and rejection behavior. It is not historical-market evidence.

The independent critic blocks promotion because:

- the split is not the trusted purged/embargoed option-replay WFA;
- option execution is not certified;
- small samples cannot satisfy the frozen trade-count gates.

Expected verdicts are rejection or, with a sufficiently large eligible candle dataset, at most `READY_FOR_OPTION_REPLAY`. The system cannot emit `READY_FOR_SHADOW` from this path.
