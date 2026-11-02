# OptionMate Premium Anchor and Strike Selection Research Note

**Status:** evidence-backed hypothesis only; exact OptionMate fidelity `NOT_MEASURABLE`; verdict `NO-GO / RESEARCH-ONLY`.

## Keep the quantities separate

The user identifies ₹28, ₹38, ₹68, ₹128, and ₹158 as option-premium price points, with selected CE/PE strikes having premiums around those prices. They are not strike identifiers and are not NIFTY index levels. This is a user-provided interpretation for an independent test, not five confirmed OptionMate values. The recording evidence below supports the existence of NIFTY chart levels and discussion of nearby option premiums, but not the entire five-number set or an exact mapping.

The recording describes five NIFTY spot chart levels (a Trend Decider and two reversal levels on each side) separately from option-chain contract discussion. Spot-level output, option premium, strike, expiry, and CE/PE side must remain separate fields. A hypothetical pipeline can map a directional spot signal to a CE/PE contract whose observed premium is near a user anchor; no evidence establishes that OptionMate implements this mapping.

## What the recording supports, with translation limits

The Telugu video and its English auto-translation were inspected on 2026-11-02. The translated captions are machine-generated and potentially inaccurate; caption authorship is unspecified. Timestamped short paraphrases are in the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). Around 4:31–5:58, the translation describes five NIFTY levels: a Trend Decider plus two reversal levels above and below. Around 6:03–6:23 it names radial-basis neural networking and discusses deriving levels/corresponding strikes, but omits implementation detail. Around 55:19–56:12 it discusses option-chain premiums including ₹38 and ₹68 and selecting a nearby strike; another amount appears as ₹138 in an earlier translated segment, creating unresolved ₹128/₹138 ambiguity. ₹28 and ₹158 are not confirmed in the cited video segments. None of these paraphrases proves a fixed anchor ladder or deterministic algorithm.

## What PR #992 implements

This section describes PR #992 head `a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f`, not OptionMate. The PR's Gaussian RBF model predicts three spot levels (upper reversal, trend decider, lower reversal); its option selector defines premium tiers ₹38/₹48/₹58/₹68/₹88/₹128; and its ranking defaults do not enforce a maximum tier distance. The inspected snapshot does not establish one end-to-end causal path joining forecast, CE/PE choice, premium selection, and replay. These are PR implementation observations only.

## Research interpretation and limits

A candidate to test is: predict/derive market reference levels; infer direction and CE/PE side from the spot's behavior around those levels; at the signal time choose a valid expiry/strike on that side whose option premium is near a configured anchor; manage the position under separately frozen stop/target rules. Only the chart-level concept, broad RBFN mention, and nearby premium/strike discussion have translated-caption support, with the stated ambiguity. Feature set, RBFN centers/width/training, five-level output construction, side mapping, anchor tolerance, tie-breaks, exits, and costs remain hypotheses.

Local conditional replay numbers are not OptionMate results or realized P&L. Rights and processed-data lineage remain incomplete; no historical quotes/fills are established. Exact fidelity remains `NOT_MEASURABLE`; verdict remains `NO-GO / RESEARCH-ONLY`. No live, paper, broker, or order behavior is authorized.

## Evidence needed

- Dated OptionMate morning levels and generation times.
- Exact corresponding instrument, expiry, strike, and CE/PE side.
- Entry, exit, rejected, and no-trade decisions.
- Clarified meaning of ₹28/38/68/128/158 and the 128/138 ambiguity.
- Licensed historical quote/fill data and defensible lineage.
- A frozen interpretation evaluated on untouched sessions.
