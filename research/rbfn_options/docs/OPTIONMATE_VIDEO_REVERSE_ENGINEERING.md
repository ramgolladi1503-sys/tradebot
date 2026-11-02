# OptionMate video reverse-engineering record

Status: evidence-informed hypothesis; exact fidelity `NOT_MEASURABLE`. Source: [OptionMate video](https://www.youtube.com/watch?v=TRTkXLYLh3M), duration 59:29. Evidence includes the Telugu original, an English machine translation inspected 2026-11-02, and direct playback review of the English YouTube auto-captions on 2026-11-03. Translation and caption rendering may be inaccurate; caption provenance/authorship is unspecified. The raw caption exports are not included in this repository. Their temporary local SHA-256 values and timestamped paraphrases are recorded in the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). No transcript quotations are reproduced here.

## Timestamped paraphrases

- 4:31: caption wording about “four prices” and “five” is ambiguous. At 4:40 the NIFTY 50 Index chart visibly shows “Reversal Price” and “Trend Decider Price” overlays. This screen observation supports chart/spot classification, but the screenshot was not committed and can be rechecked at this timestamp; exact overlay count/formula remain unresolved.
- 5:21–5:41: translated captions mention CPR/pivot points and support/resistance, and appear to distinguish the discussed levels from pivot points; the wording does not identify a calculation.
- 6:11: caption renders the unqualified number “138”; meaning, currency/unit, and relation to other values are unresolved.
- 6:21: corresponding strike prices are mentioned. Around 6:31–6:51 an RBFN family/reference is mentioned, without model mechanics or a disclosed output-to-strike mapping.
- 7:21–8:45: translated explanation relates movement above/below Trend Decider to direction and successive reversal levels as targets.
- 8:50–9:52 and 21:34–23:16: translated discussion covers reversals near levels, nearby reversal confluence and retests; discretionary meaning is not formalized.
- 10:41–15:48: discussion includes ATM/OTM premiums, delta and risk/reward; translated numerical examples are uncertain.
- 23:32–26:11: an early reversal-level break is described as possible trend continuation; the approximate time is a heuristic, not a verified hard cutoff.
- 27:24–29:53: translated examples mention approximate stop distances and risk/reward; do not treat them as fixed rules.
- 38:40–38:55: caution around Trend Decider.
- 43:34–43:57: caution about new trades later in the afternoon.
- 46:50–47:14: speaker appears to emphasize price sustainability/respect of levels over other technical indicators; translation and surrounding examples leave exact procedure uncertain.
- 55:27/55:39: translated captions mention option-chain values 38 and 68; a third price is unclear. At 56:08 the captions mention selecting that strike. This narrowly supports nearby option-chain discussion, not the derivation of those values or a deterministic selector.

These are short paraphrases of translated-caption evidence, not verbatim transcript or verified source labels. The early chart/spot overlays and later option-chain examples are distinct in the evidence; their relationship is unresolved. The user's `USER_CLARIFICATION` that RBFN-derived premium values ₹28/₹38/₹68/₹128/₹158 precede nearby-strike selection is not confirmed by these captions. The exact overlay count/definition, learning target, input features, RBFN architecture/training, premium output semantics, contract selection, and order management are not disclosed by this source evidence. The unqualified 138 at 6:11 has unresolved meaning/unit and no supported link to the later examples or user clarification.

## Reverse-engineering boundary

A plausible research decomposition is (1) calculate/forecast spot reference levels, (2) classify trend/reversal behavior and direction, (3) select CE or PE, (4) find a nearby-strike contract around a premium cue, and (5) apply risk/exit rules. Steps 1–5 are not an exact recovered implementation. Only the broad level and option discussion is supported by translated paraphrase; details are open hypotheses. Generic Gaussian RBF equations cannot identify OptionMate's learned function without training data/model outputs.

The independently coded research analogue and PR #992 are distinct implementations. They are not OptionMate source code or ground truth. Telegram calls are separately sourced recommendations, not fills or model internals. No selected strategy or performance figure establishes fidelity. See the synthesis and evidence register. No live actions are authorized.
