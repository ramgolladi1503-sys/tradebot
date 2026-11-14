# Current TradeBot Context

## Identity

TradeBot is a flagship Aixion Lab system focused on reliability, observability, failure handling, market-data correctness, risk controls, execution-state transparency, research discipline, and reproducible evidence.

It must not be treated as a profitability demo.

## Operating invariants

- `AGENTS.md` is the authoritative agent-safety contract.
- No agent may place, modify, cancel, or exit orders.
- No hidden broker calls.
- Do not weaken risk, kill-switch, feed-freshness, or runtime safety controls.
- Preserve SIM / PAPER / LIVE boundaries.
- Do not make strategy or runtime changes outside explicit scope.
- Evidence must describe what actually ran.
- Missing evidence is a blocker, not permission to invent.
- Tests must prove behavior rather than shallow object construction.

## Context-loading policy

For engineering tasks, load only:
- this file;
- `.aixion/project.yaml`;
- `AGENTS.md`;
- affected source/tests;
- directly relevant release/safety docs.

For research tasks, additionally load:
- the specific research artifact(s);
- related durable failure records;
- relevant evidence records;
- only the dataset manifest needed for the hypothesis.

Do not load the entire research history by default.

## Research loop

question
-> mechanism/hypothesis
-> cheap deterministic screen
-> bounded backtest
-> robustness/WFA/cost checks
-> verdict
-> evidence record
-> failure record when rejected

Repeated attempts must materially change the mechanism, data, or test. Renaming/reparameterizing the same failed idea is not a new experiment.

## Engineering loop

task packet
-> scoped implementation
-> focused tests
-> full required verification
-> health gate when safety-sensitive
-> evidence record
-> PR

## Session-end extraction

Persist only durable changes:
- proven fix;
- failed approach and root cause;
- changed invariant;
- architecture decision;
- reusable command;
- evidence pointer.

Do not persist generic conversation summaries.
