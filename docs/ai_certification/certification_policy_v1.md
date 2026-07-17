# Backtest Certification Policy v1

## Authority

Only `core.option_backtest.engine.OptionBacktestEngine` running in `REAL_EXECUTABLE_RESEARCH` mode together with `core.option_backtest.wfa.run_option_replay_wfa` may produce certifying evidence.

Legacy, vectorized, synthetic, fallback-liquidity, hardcoded-metric, or proxy execution paths are non-certifying.

## Mandatory gates

A bundle must prove immutable artifact hashes, dataset provenance, causal timing, executable-side fills, explicit cost reconciliation, chronological and isolated walk-forward partitions, negative controls, and green test evidence from the recorded repository commit.

Missing mandatory evidence produces `INSUFFICIENT_EVIDENCE`. Contradictory or invalid mandatory evidence produces `REJECTED`. Validator failures produce `AGENT_ERROR`.

## Separation of concerns

Evidence certification and strategy performance are independent. A valid experiment may be certified while concluding `NO_STRUCTURAL_EDGE`. An invalid experiment cannot support any profitability conclusion.

## Safety boundary

The certification package is read-only with respect to TradeBot. It exposes no broker, order, strategy mutation, risk override, arbitrary shell, database mutation, or Git write capability.
