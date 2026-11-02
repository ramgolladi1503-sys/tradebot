# OptionMate Premium Anchor and Strike Selection Research Note

**Status:** hypothesis; exact OptionMate fidelity `NOT_MEASURABLE`; research verdict `NO-GO / RESEARCH-ONLY`.

## Scope

This note separates three things that are easy to conflate:

1. The user's interpretation of the values ₹28, ₹38, ₹68, ₹128, and ₹158 as option-premium cues for finding a CE or PE contract.
2. The strike identity of the contract selected from the option chain: underlying, expiry, strike, and CE/PE side.
3. The code in PR #992 at the specific revision reviewed below.

The first is a user-provided interpretation. The third describes repository code. Neither establishes the proprietary OptionMate strategy.

## User-provided premium interpretation

The user's current explanation is that ₹28/₹38/₹68/₹128/₹158 are prices associated with options, and that the selected strikes are contracts whose premiums are around those values. Under that interpretation, a premium value is not a strike price or an index level. A selected option remains identified separately by its underlying, expiry, strike, and CE/PE side.

This is a useful hypothesis for testing a contract-selection rule. It is not yet verified against a timestamped OptionMate output or a preserved, annotated video frame. The available material does not establish which of the values are entry cues, target levels, forecast levels, examples, or fixed ladder tiers.

## What PR #992 implements

The following statements refer only to PR #992 head `a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f`, not to OptionMate.

- [`spot_boundary_model.py` at the reviewed PR head](https://github.com/ramgolladi1503-sys/tradebot/blob/a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f/research/rbfn_options/core/spot_boundary_model.py) uses a Gaussian RBF model to forecast three spot levels: upper reversal, trend decider, and lower reversal.
- [`low_premium_strike_selector.py` at the reviewed PR head](https://github.com/ramgolladi1503-sys/tradebot/blob/a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f/research/rbfn_options/core/low_premium_strike_selector.py) defines six option-premium tiers: ₹38, ₹48, ₹58, ₹68, ₹88, and ₹128.
- In `MultiStrikeChainRanker.rank_chain_at_timestamp`, the implementation filters to the requested date and option side, limits rows to timestamps at or before the evaluation time, chooses the nearest expiry not earlier than the date, and uses each contract's latest available bar. By default, `max_tier_distance` and `max_spread_pct` are unset. Thus, the default call does not enforce a maximum distance from a tier. Its ranking score includes a spread term only when bid and ask are available; with no valid spread, the spread contribution is zero. No delta term appears in this rank score.
- `select_low_premium_strike` and `select_strike_at_touch` are separate functions with different input-time filtering and ranking surfaces. They should not be treated as one uniform selector without evidence about which call path is used.
- [`strike_reversal_replay.py` at the reviewed PR head](https://github.com/ramgolladi1503-sys/tradebot/blob/a626a3eaa6a9c6e3d5fccb5f192ca25b65daad6f/research/rbfn_options/core/strike_reversal_replay.py) checks a reclaim of `reference_level` against the option candle's close and enters on the next option candle's open. The reviewed PR snapshot does not establish an end-to-end call path connecting the spot forecast, CE/PE choice, premium-tier selector, and replay.

These are implementation details at one pinned PR revision. They do not show that OptionMate uses the same model, levels, tiers, defaults, or replay rules.

## Recording evidence and limits

The supplied [OptionMate recording](https://www.youtube.com/watch?v=TRTkXLYLh3M) is titled “AI-Based Trading Strategy in Telugu (Step by Step Guide).” On 2026-11-02, the player reported captions unavailable and a transcript export returned no transcript. No transcript, source-frame capture, or capture hash is preserved with this research.

That observation describes the check on that date; it does not prove captions were never available. Without a timestamped transcript or preserved frames, prior descriptions of what the speakers said or displayed remain unverified. The recording cannot currently establish that OptionMate uses an RBFN, the five premium values above, a particular strike-selection rule, or any specific entry, exit, stop, or timing rule.

## Research conclusion

The code and evidence support a candidate interpretation to test:

> A model produces a market reference; at a decision time, the trader chooses a CE or PE contract whose option premium is near a selected premium cue, while keeping expiry and strike as separate contract fields.

The available evidence does not show that this is OptionMate's actual algorithm. Exact fidelity remains `NOT_MEASURABLE`. The research verdict remains `NO-GO / RESEARCH-ONLY`.

No local historical performance figures are included in this note. The option source's use and redistribution terms remain unverified, so vendor-derived counts, coverage tables, contract rows, and INR results are excluded pending rights and lineage review. Existing conditional replay figures are not realized P&L and are not OptionMate results.

## Evidence required to test the hypothesis

- Preserved, timestamped video frames or a transcript tied to the recording, with provenance.
- OptionMate outputs keyed to date, underlying, generation time, expiry, strike, and CE/PE side.
- The meaning of each premium cue and whether it represents an entry, forecast, target, or another reference.
- Entry, exit, rejection, and no-trade decisions with timestamps for exact selected contracts.
- A documented end-to-end path from RBFN output to spot signal, option-side choice, contract selection, and replay.
- Licensed historical option data with verified source-to-output lineage and execution assumptions before publishing data-derived results.
- A frozen interpretation and untouched held-out period for any fidelity or profitability evaluation.

No live, paper, broker, or order behavior is authorized by this research note.
