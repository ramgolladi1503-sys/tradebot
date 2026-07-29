# Nested Causal Rule Discovery V1

Research-only search for a higher-occurrence NIFTY buy-option edge without manually inventing another threshold combination.

At each minute, one representative CE and PE are selected using premium distance and liquidity only. A depth-three decision tree is trained on prior sessions with a winsorized return after 1% total friction. Candidate leaves must be broad, concentration-resistant and positive across at least two of three chronological inner blocks before being frozen and applied to the next outer WFA fold.

Governance:

- causal features only;
- maximum depth three and at most two selected leaves;
- four expanding outer WFA folds;
- fixed label-permutation pipeline as a negative control;
- at least 100 OOF signals across 70 sessions;
- latest 25% chronological holdout opened only after the aggregate OOF gate;
- mirror-wing and five-minute-delay holdout controls;
- no post-outcome model-depth, leaf-size or gate changes;
- historical five-minute candle proxy only;
- no broker, paper, live or production action.
