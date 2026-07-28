# Market Story Engine V1 — Research Contract

## Agent Work Contract

Implement screenshot-style analysis as five causal layers rather than another flat indicator strategy:

1. dynamic structural map;
2. ordered market-state machine;
3. participation and opportunity quality;
4. option repricing and liquidity confirmation;
5. fail-closed `BUY_CE` / `BUY_PE` / `WAIT` / `REJECT` construction.

The implementation must remain causal, deterministic, research-only, auditable, and disconnected from broker/order/live authority.

## Scope Guard

Changed scope is limited to a new research package, two research scripts, one focused test file, one isolated workflow, and this review document.

No production strategy registration, strategy thresholds, candidate ranking, risk, execution, broker, feed, dashboard, credentials, deployment, Telegram, paper configuration, or live configuration is changed. Inputs are caller-supplied historical/replay data frames. The engine has no broker client and no order method.

## Grill Me Review

The strongest challenge is that a richer market narrative can still be sophisticated overfitting. The implementation therefore does not claim that its state names or thresholds have economic value. It only proves that the declared causal mechanics behave consistently under adversarial fixtures.

Specific challenges checked:

- The same terminal area reached through acceptance versus a failed break produces different decisions.
- Weak breadth cannot be rescued by a bullish candle.
- Weak CE/PE repricing cannot be rescued by bullish or bearish underlying structure.
- Missing, crossed, stale, or underlying-misaligned option evidence blocks the trade.
- Extra EMA and Supertrend columns do not influence the result.
- Future rows cannot alter already-produced decisions.

Review status: implementation objections addressed for the bounded robustness claim. Economic edge remains unproven.

## Hermes Review

Data and temporal integrity review:

- all three inputs require explicit timestamps and required schema fields;
- duplicate and non-monotonic timestamps fail closed;
- joins are backward-only with a 75-second tolerance;
- option rows include a synchronized underlying reference and are rejected on mismatch;
- prefix-invariance tests prove later rows do not change earlier decisions;
- shifted option timestamps do not retain a buy decision;
- no future outcome, trade result, MFE, MAE, target hit, or PnL field is consumed by signal generation.

Review status: causal input boundary passes the focused contract.

## GSD Review

Architecture review:

- `structure.py` owns dynamic levels, compression, candle quality, room, and overextension;
- `state.py` owns ordered semantic states;
- `confirmations.py` owns breadth/concentration and CE/PE response checks;
- `engine.py` owns validation, causal joining, and fail-closed decisions;
- `certification.py` owns deterministic scenario and mutation-resistant evidence generation;
- the independent auditor reimplements artifact checks and does not import the engine package.

The implementation deliberately avoids a single opaque research script and avoids counting correlated price indicators as independent confirmations.

Review status: module boundaries and responsibilities are explicit and testable.

## QA / Safety Review

Focused checks cover:

- bullish `BUY_CE` and bearish `BUY_PE` symmetry;
- failed-break `WAIT` behaviour;
- weak-breadth, weak-option, missing-option, and crossed-market rejection;
- duplicate and unsorted timestamp rejection;
- future-data prefix invariance;
- option timestamp-shift control;
- redundant-indicator non-influence;
- at least 90% decision stability under small perturbations in both directions;
- deterministic repeated certification;
- independent-auditor import separation;
- tampered-certification detection.

Safety flags are emitted in every decision and certification artifact:

- `research_only=true`;
- `allowed_for_live_execution=false`;
- `broker_api_called=false`;
- `is_order_action=false`.

QA status: focused local suite passed before publication, and the isolated GitHub workflow independently passed compile, tests, certification, audit, determinism comparison, and artifact upload.

## Acceptance Proof

Accepted bounded result:

- local focused tests: `15 passed`;
- certification verdict: `PASS_IMPLEMENTATION_ROBUSTNESS_GATE`;
- independent oracle verdict: `PASS_INDEPENDENT_AUDIT`;
- GitHub workflow `Market Story Engine V1`: successful;
- two independent workflow certification runs produced matching semantic hashes;
- synthetic noise stability threshold: at least `0.90` for bullish and bearish scenarios;
- tampered evidence is rejected by semantic-hash and content checks.

Acceptance is limited to deterministic implementation robustness. It is not acceptance of market profitability.

## Machine-Readable Evidence Contract

- mode: RESEARCH
- candidate_id: MARKET_STORY_ENGINE_V1_IMPLEMENTATION_ROBUSTNESS
- decision: PASS_IMPLEMENTATION_ROBUSTNESS_GATE
- reason: The five-layer causal engine passed deterministic robustness, adversarial controls, and an implementation-independent audit; economic edge remains unproven.
- timestamp: 2026-07-28T19:30:00+05:30
- is_order_action: false
- broker_api_called: false
- source: GitHub Actions Market Story Engine V1 run 30366017470 on commit bafd32cf6e40fcadbe384157f5baef5d0df6512c

## Runtime Proof Required After Merge

This PR should remain draft and unmerged. Before any later runtime integration, a separate human-reviewed campaign must prove all of the following on authoritative synchronized data:

1. exact underlying, constituent-breadth, and option-contract provenance;
2. a frozen pre-outcome market-story specification;
3. chronological development, validation, and untouched holdout partitions;
4. next-bar option entry with conservative OHLCV execution assumptions or executable ask-entry/bid-exit quotes;
5. spread, slippage, brokerage, taxes, and quantity constraints;
6. CE, PE, expiry, strike, regime, and time-of-day stability;
7. matched-time, direction-flip, delayed-entry, shuffled-session, and component-ablation controls;
8. walk-forward survival and concentration checks;
9. forward shadow evidence before paper eligibility;
10. separate explicit human approval before any production wiring.

## What This PR Does Not Prove

This PR does not prove:

- a structural market edge;
- profitable historical CE/PE trading;
- transaction-cost survival;
- positive expectancy or profit factor;
- walk-forward or untouched-holdout survival;
- that the chosen thresholds are optimal or economically stable;
- paper readiness;
- live readiness;
- authority to place, modify, or cancel an order.

Synthetic fixtures prove behavior and failure modes, not market profitability.

## Human Approval

Human approval is required before:

- merging this draft PR;
- binding the engine to the authoritative local corpus for an economic campaign;
- changing frozen thresholds after outcome access;
- registering a production strategy;
- enabling paper or shadow candidate emission outside research;
- connecting any broker, risk, execution, notification, or live path.

Current approval state: not granted. PR must remain draft and unmerged.
