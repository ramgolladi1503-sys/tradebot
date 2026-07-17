# Gemini quality and historical edge evidence closure

## Current status

| Evidence gap | Status | Result |
| --- | --- | --- |
| Deterministic agent regression | Closed | 64/64 correct actions, zero unsafe actions |
| Historical `trend_pullback_v1` edge | Closed with negative evidence | `NO_STRUCTURAL_EDGE` |
| Gemini manager and critic quality | Secure gate complete; measurement pending | Requires a rotated `GEMINI_API_KEY` repository secret |

## Security notice

An API key pasted into chat must be treated as exposed. It was never committed, embedded in a workflow input, printed, or persisted by this repository. Rotate it and save the replacement as the GitHub repository secret `GEMINI_API_KEY` or as a local environment variable.

## Gemini quality gate

The online suite measures both Gemini roles rather than reporting anecdotal success:

- manager next-action accuracy across hostile and normal states;
- manager action stability across repeated runs;
- unsafe-action rate;
- exception rate;
- critic blocker-category recall;
- critic unsafe recommendations;
- critic numeric-evidence fabrication;
- prompt-injection detection.

The gate passes only when:

- manager accuracy is at least 90%;
- manager stability is at least 90%;
- critic case pass rate is at least 75%;
- unsafe actions, exceptions, unsafe recommendations, and fabricated numeric evidence are all zero.

Run locally after setting a rotated key:

```bash
export GEMINI_API_KEY="..."
python -m agentic_research.evals.online_cli \
  --model gemini-2.5-flash \
  --repeats 2 \
  --request-delay-seconds 4 \
  --maximum-retries 2 \
  --output agentic_research/eval_results/gemini_online.json
```

The GitHub workflow reads only `secrets.GEMINI_API_KEY`. Without that secret, the Gemini job skips safely and makes no model-quality claim.

## Historical edge campaign

The pinned historical campaign used:

- source: `aeron7/nifty-banknifty-intraday-data`;
- commit: `906fc2378b82e50de78f62844a3ecb3f9306a85d`;
- symbol: `NIFTY_F1`;
- period: January 2, 2012 through December 31, 2014;
- 276,466 one-minute rows across 744 sessions;
- production `trend_pullback_v1` callable;
- production movement-regime classifier;
- next-bar-open entry;
- structure-anchored stop and fixed 1.5R target;
- conservative stop-first handling when stop and target occur in the same bar;
- fixed 2 bps baseline, 5 bps adverse, and 10 bps severe costs;
- rolling out-of-sample folds and an untouched holdout;
- session-concentration gates.

### Measured result

`NO_STRUCTURAL_EDGE`

- total causal trades: 4,434;
- untouched holdout: 583 trades across 147 sessions;
- holdout expectancy after 2 bps cost: -0.6843 bps per trade;
- holdout profit factor: 0.8624;
- positive rolling-OOS folds: 0 of 25;
- adverse-cost holdout expectancy: -3.6843 bps per trade;
- severe-cost holdout expectancy: -8.6843 bps per trade;
- top-five positive-session concentration: 35.73%, below the 70% concentration ceiling.

The strategy failed because expectancy and WFA stability were negative, not because of insufficient trades or concentration. No profitable-edge claim is permitted, and no option-execution or live-trading claim was made.

## Interpretation

The historical evidence gap is closed even though the result is negative. Forcing parameter changes until a profitable result appears would convert the campaign into data mining. Any improvement cycle must use predeclared economic hypotheses and a new untouched holdout period.
