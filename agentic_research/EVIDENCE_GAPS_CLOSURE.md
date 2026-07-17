# Gemini quality and historical edge evidence gates

## Security notice

An API key pasted into chat must be treated as exposed. It is never committed, embedded in a workflow input, printed, or persisted by this repository. Rotate it and save the replacement as the GitHub repository secret `GEMINI_API_KEY` or as a local environment variable.

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
  --output agentic_research/eval_results/gemini_online.json
```

The GitHub workflow reads only `secrets.GEMINI_API_KEY`. If the secret is absent, the Gemini job skips safely and makes no quality claim.

## Historical edge campaign

The pinned historical campaign uses:

- source: `aeron7/nifty-banknifty-intraday-data`;
- commit: `906fc2378b82e50de78f62844a3ecb3f9306a85d`;
- symbol: `NIFTY_F1`;
- years: 2012–2014;
- production `trend_pullback_v1` callable;
- production movement-regime classifier;
- next-bar-open entry;
- structure-anchored stop and fixed 1.5R target;
- conservative stop-first handling when stop and target occur in the same bar;
- fixed 2 bps baseline, 5 bps adverse, and 10 bps severe costs;
- rolling out-of-sample folds and an untouched holdout;
- session-concentration gates.

Possible verdicts:

- `INVALID_DUE_TO_DATA`;
- `NO_STRUCTURAL_EDGE`;
- `STRUCTURAL_EDGE_CANDIDATE`.

Even the strongest verdict is futures-level structural evidence only. It does not certify option fills or live profitability.
