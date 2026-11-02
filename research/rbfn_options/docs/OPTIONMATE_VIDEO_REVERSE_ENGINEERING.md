# OptionMate video reverse-engineering record

Status: evidence-informed hypothesis; exact fidelity `NOT_MEASURABLE`. Source: [OptionMate video](https://www.youtube.com/watch?v=TRTkXLYLh3M), duration 59:29. Evidence is the Telugu original plus an English machine translation inspected 2026-11-02. Translation may be inaccurate; caption authorship is unspecified. The raw caption exports are not included in this repository. Their temporary local SHA-256 values and timestamped paraphrases are recorded in the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). No transcript quotations are reproduced here.

## Timestamped paraphrases

- 4:31–5:58: translated speech describes five NIFTY spot levels: one Trend Decider and two reversal levels on either side; it distinguishes the concept from CPR/pivot levels.
- 6:03–6:23: speaker names radial-basis neural networking and describes deriving levels/corresponding strikes; no model details are provided.
- 7:21–8:45: translated explanation relates movement above/below Trend Decider to direction and successive reversal levels as targets.
- 8:50–9:52 and 21:34–23:16: translated discussion covers reversals near levels, nearby reversal confluence and retests; discretionary meaning is not formalized.
- 10:41–15:48: discussion includes ATM/OTM premiums, delta and risk/reward; translated numerical examples are uncertain.
- 23:32–26:11: an early reversal-level break is described as possible trend continuation; the approximate time is a heuristic, not a verified hard cutoff.
- 27:24–29:53: translated examples mention approximate stop distances and risk/reward; do not treat them as fixed rules.
- 38:40–38:55: caution around Trend Decider.
- 43:34–43:57: caution about new trades later in the afternoon.
- 46:50–47:14: speaker appears to emphasize price sustainability/respect of levels over other technical indicators; translation and surrounding examples leave exact procedure uncertain.
- 55:19–56:12: translated discussion explicitly includes ₹38 and ₹68 option premiums and selecting a nearby chain strike; an earlier translated amount is ₹138, so mapping to user-provided ₹128 remains unresolved. ₹28 and ₹158 are not confirmed in these cited segments.

These are short paraphrases of translated-caption evidence, not verbatim transcript or verified source labels. The video distinguishes the five NIFTY chart levels from nearby option-chain premiums. The exact definition of each level, the learning target, input features, RBFN architecture/training, premium tier ladder, contract selection, and order management are not disclosed by this source evidence.

## Reverse-engineering boundary

A plausible research decomposition is (1) calculate/forecast spot reference levels, (2) classify trend/reversal behavior and direction, (3) select CE or PE, (4) find a nearby-strike contract around a premium cue, and (5) apply risk/exit rules. Steps 1–5 are not an exact recovered implementation. Only the broad level and option discussion is supported by translated paraphrase; details are open hypotheses. Generic Gaussian RBF equations cannot identify OptionMate's learned function without training data/model outputs.

The independently coded research analogue and PR #992 are distinct implementations. They are not OptionMate source code or ground truth. Telegram calls are separately sourced recommendations, not fills or model internals. No selected strategy or performance figure establishes fidelity. See the synthesis and evidence register. No live actions are authorized.
