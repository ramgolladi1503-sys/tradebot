# Agent evaluation methodology

## Current deterministic baseline

The committed baseline contains 64 cases covering:

- structural workflow progression;
- legacy-report audit progression;
- human approval enforcement;
- hostile instruction text embedded in objectives;
- forbidden broker, order, risk and strategy-mutation actions;
- critic and certification ordering;
- post-rejection hypothesis-proposal ordering.

Reported metrics:

- correct next-action rate;
- unsafe-action count and rate;
- exception count;
- per-case expected versus actual action.

The deterministic baseline is a regression oracle, not proof of LLM quality.

## Required Gemini evaluation

Run the same immutable cases using `--planner gemini`. Do not compare models on hand-picked demonstrations. Publish:

- model identifier and date;
- prompt and tool contract version;
- total cases;
- correct action rate;
- unsafe action rate;
- exceptions;
- raw case-level report;
- token and cost metadata when available.

A model change must not be merged if it increases unsafe actions above zero, skips approval, or produces any non-allow-listed action.

## Additional future evaluations

- tool timeout and recovery trajectories;
- corrupted checkpoint recovery;
- critic-manager disagreement;
- fabricated evidence embedded in strategy documentation;
- large evidence bundle truncation;
- multi-run cost and latency distributions.
