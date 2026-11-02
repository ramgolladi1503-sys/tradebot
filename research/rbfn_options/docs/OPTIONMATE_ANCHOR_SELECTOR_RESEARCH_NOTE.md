# OptionMate Premium Anchor and Strike Selection Research Note

**Status:** evidence-backed hypothesis only; exact OptionMate fidelity `NOT_MEASURABLE`; verdict `NO-GO / RESEARCH-ONLY`.

## Keep the quantities separate

The user clarifies that ₹28, ₹38, ₹68, ₹128, and ₹158 are **option-premium values derived by the RBFN**, after which strikes with premiums around those values are selected. These are not described as static, user-defined tier targets, strike identifiers, or NIFTY index levels. This `USER_CLARIFICATION` is not independently verified by the recording or an authenticated source. The exact role of each value remains unresolved: whether they are five simultaneous bands, which contract/side and forecast time they apply to, and which value triggers strike selection are unknown.

The translated transcript discusses multiple NIFTY chart/spot prices or overlays, including Trend Decider and reversal terminology. The 4:40 playback screen shows a NIFTY 50 Index chart with “Reversal Price” and “Trend Decider Price” overlays; the screenshot was not committed and can be rechecked at that timestamp. Caption wording around 4:31 about four prices and five is ambiguous, so the exact number of levels is not established. This chart evidence does not connect the spot overlays to later option-chain premium examples or prove they are the user's values ₹28/₹38/₹68/₹128/₹158. Spot-level output, RBFN-derived option premium, observed option premium, strike, expiry, and CE/PE side must remain distinct quantities and fields.

## What the recording supports, with translation limits

The Telugu video and its English auto-translation were inspected on 2026-11-02; the English YouTube auto-captions were reviewed during direct playback on 2026-11-03. The captions are machine-generated or translated, potentially inaccurate, and of unspecified authorship/provenance; the timestamped entries are paraphrases, not exact quotations. See the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). Early captions discuss chart/spot prices or levels, including Trend Decider, reversal/sideways movement, support/resistance, and a phrase rendered “AA based factors”; the count wording is ambiguous. At 4:40, playback shows a NIFTY 50 Index chart with “Reversal Price” and “Trend Decider Price” overlays (the screenshot was not committed; the timestamp can be rechecked). This supports chart/spot classification, not an exact count or formula. A later segment separately mentions an important NIFTY price, three prices (including 38 and 68, with a third unclear), option-chain values, and selecting a strike. The unqualified 138 at 6:11 has unresolved meaning, currency/unit, and relation to other values; no supported link to the later option-chain examples or the user's clarification. The RBFN-family mention around 6:31–6:51 supplies no mechanics. No evidence connects an RBFN output to the user's five values ₹28/₹38/₹68/₹128/₹158, or connects the early chart overlays to later premium examples. The user's clarification that the RBFN derives these option-premium values before nearby-strike selection remains an unverified hypothesis, not a transcript-confirmed algorithm.

## What PR #992 implements

This section describes PR #992 head `a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f`, not OptionMate. The PR's Gaussian RBF model predicts three spot levels (upper reversal, trend decider, lower reversal); its option selector defines premium tiers ₹38/₹48/₹58/₹68/₹88/₹128; and its ranking defaults do not enforce a maximum tier distance. The inspected snapshot does not establish one end-to-end causal path joining forecast, CE/PE choice, premium selection, and replay. These are PR implementation observations only.

## Research interpretation and limits

A candidate to test is: derive spot reference levels and/or CE/PE premium values with a model; determine the applicable CE/PE side and contract context; then select a valid expiry/strike whose contemporaneously observed premium is near a model-derived value; manage any position under separately frozen rules. This decomposition reflects the user's `USER_CLARIFICATION` as a hypothesis. The translated transcript and playback separately support chart/spot overlays, a broad RBFN mention, and later nearby option-premium/strike discussion, but do not establish an exact chart-level count or connect those overlays to five model-derived premium values. Feature set, RBFN centers/width/training, premium-value output construction, contract-selection timing and tolerance, tie-breaks, exits, and costs remain hypotheses.

## What the three local experiments do (and do not) test

- `premium_rbfn_pilot.py` selects nearest-expiry ATM CE and PE contracts first using information available at 09:19. It trains on three normalized outcomes for those selected contracts: remaining-session high-premium excursion, low-premium excursion, and close return. Post-processing derives three inner premium bands and two outer bands from training-only residual quantiles. Thus it does **not** learn five premium values and then scan the chain for nearby strikes as the user describes.
- `video_strategy_analogue.py` is a separate fixed-premium-anchor hypothesis layered onto an independent spot-level analogue. Its fixed anchors do not test whether the RBFN itself derives the five premium values before strike selection.
- PR #992 is a separate implementation with a three-level spot forecast and hardcoded premium tiers. Its implementation is not evidence that OptionMate works that way, nor that it implements the user's clarified model-output-to-strike-selection sequence.

Any existing INR replay metrics are from the ATM-first/local replay and are conditional on incomplete data lineage, assumed execution costs and OHLC fills; the 2026 period was reused across local variants. They cannot be attributed to the clarified RBFN-derived-premium-then-nearby-strike strategy, and are not verified realized net returns or OptionMate results. Rights and processed-data lineage remain incomplete; no historical quotes/fills are established. Exact fidelity remains `NOT_MEASURABLE`; verdict remains `NO-GO / RESEARCH-ONLY`. No live, paper, broker, or order behavior is authorized.

## Evidence needed

- Dated OptionMate morning levels and generation times.
- Exact corresponding instrument, expiry, strike, and CE/PE side.
- Entry, exit, rejected, and no-trade decisions.
- Authenticated clarification of the RBFN-derived ₹28/38/68/128/158 values: their output semantics, forecast time, contract context, and rule for selecting a nearby strike. The unqualified 138 caption's meaning, unit, and relation to other values remain unknown.
- Authenticated, timestamped source evidence that joins a model-generated premium value to the relevant CE/PE side, expiry, strike-selection event, and contemporaneous option-chain premium; clarification of whether/how the early spot-level discussion relates to that later premium-chain discussion.
- Licensed historical quote/fill data and defensible lineage.
- A frozen interpretation evaluated on untouched sessions.
