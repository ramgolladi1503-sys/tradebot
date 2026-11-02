# OptionMate premium and strike observations — 2026-11-02

**Status:** source observations and bounded hypotheses only. Exact strategy/model fidelity `NOT_MEASURABLE`; verdict `NO-GO / RESEARCH-ONLY`.

## Evidence boundary

This report separates translated video captions from public Telegram examples and user hypotheses. The video was inspected 2026-11-02. Telugu original and English auto-translation exports were captured locally; exported language metadata says Telugu, while English text is machine translation. Caption authorship is unspecified and translation is error-prone. Raw exports are temporary and not committed; their hashes are in the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md). No immutable Telegram page capture is preserved; displayed timestamps may not be publication times. Calls are not verified fills or outcomes.

## Video paraphrases

During direct playback review on 2026-11-03, the 4:31 English-caption wording about four prices and five was ambiguous. At 4:40 the NIFTY 50 Index chart visibly showed “Reversal Price” and “Trend Decider Price” overlays; the screenshot was not committed and can be rechecked at that timestamp. This supports chart/spot classification, but not an exact overlay count or formula. Around 6:11 the caption renders the unqualified number 138; its meaning, currency/unit, and relation to other values are unresolved. Later captions around 55:27/55:39 mention option-chain values 38 and 68, with a third price unclear, and around 56:08 mention selecting a strike. This is narrow support for nearby-chain discussion only. No evidence connects the early chart overlays or an RBFN output to the user's `USER_CLARIFICATION` values ₹28/₹38/₹68/₹128/₹158. These are timestamped paraphrases, not quotations; provenance/authenticity/translation remain uncertain. See the [transcript evidence register](OPTIONMATE_TRANSCRIPT_EVIDENCE_REGISTER_20261102.md) for limits. The screen overlays, later option premiums, and strike identifiers must remain distinct.

## Public OptionMate call examples

Direct post links below point to the public OptionMate channel. Times are source-displayed/captured values; only the six posts with captured source timestamps explicitly marked UTC are converted to IST. Displayed times are not guaranteed actual publication times. The public source's saved raw HTML is not retained, so these records are not independently re-checkable from a preserved capture. Posts are recommendations, not verified fills, exits, or realized outcomes.

| Post | Source-displayed time/date | Timezone basis | Converted IST (where source time is UTC) | Instrument / expiry as displayed | Buy premium | Stop as displayed | Target premiums | Evidence use |
|---|---|---|---|---|---:|---:|---|---|
| [18518](https://t.me/OptionMateEducation/18518) | 27 Oct 2026 08:51 | Browser-rendered; timezone unknown | — | BankNifty 53800 PE, 27 Oct 2026 | 58 | 30 | 95 / 128 / 168 | Example premium-entry/target ladder. |
| [18519](https://t.me/OptionMateEducation/18519) | 27 Oct 2026 08:53 | Browser-rendered; timezone unknown | — | BankNifty 54800 CE, 27 Oct 2026 | 38 | 10 | 68 / 95 / 118 | Example premium-entry/target ladder. |
| [18526](https://t.me/OptionMateEducation/18526) | 27 Oct 2026 07:02:24 | UTC, as displayed in captured source | 27 Oct 2026 12:32:24 | BankNifty 54300 CE, 27 Oct 2026 | 88 | 50 | 128 / 168 / 218 | Example premium-entry/target ladder. |
| [18527](https://t.me/OptionMateEducation/18527) | 27 Oct 2026 08:28:10 | UTC, as displayed in captured source | 27 Oct 2026 13:58:10 | BankNifty 53900 CE, 27 Oct 2026 | 88 | 50 | 128 / 168 / 218 | Second example; does not prove the same signal or a universal tier. |
| [18528](https://t.me/OptionMateEducation/18528) | 27 Oct 2026 08:41:03 | UTC, as displayed in captured source | 27 Oct 2026 14:11:03 | BankNifty 54100 CE, 27 Oct 2026 | 28 | 0 | 58 / 88 / 118 | Example premium-entry/target ladder; zero is recorded as shown, not interpreted as an executable stop. |
| [18529](https://t.me/OptionMateEducation/18529) | 27 Oct 2026 09:16:00 | UTC, as displayed in captured source | 27 Oct 2026 14:46:00 | Reply repeating post 18528 | 28 | 0 | 58 / 88 / 118 | Reply text characterizes premium 88 as high; not independently validated market data or an exit. |
| [18540](https://t.me/OptionMateEducation/18540) | 29 Oct 2026 08:31:46 | UTC, as displayed in captured source | 29 Oct 2026 14:01:46 | Sensex 73800 PE, 29 Oct 2026 | 28 | 0 | 58 / 95 / 118 | Cross-instrument example; edited marker observed. |
| [18541](https://t.me/OptionMateEducation/18541) | 29 Oct 2026 08:33:48 | UTC, as displayed in captured source | 29 Oct 2026 14:03:48 | Sensex 74000 CE, 29 Oct 2026 | 28 | 0 | 58 / 95 / 118 | Cross-instrument example; similarity does not establish paired execution. |

These posts display varying entry/stop/target premiums. They do not prove a universal ladder, RBFN output vector, video claim, strike-selection rule, or execution outcome. The user's `USER_CLARIFICATION` that the RBFN derives values ₹28/38/68/128/158 before nearby-strike selection remains a hypothesis; this public-call sample does not establish that mapping. Some calls separately display 128 as a target, while 158 is absent from this bounded sample; those observations are separate and do not establish a relation to the unqualified caption number 138. Do not reinterpret the user's values as index points or strike IDs.

## Fidelity and follow-up

Exact fidelity cannot be scored without dated OptionMate spot levels, generation timestamps, instrument/expiry/strike/CE-PE, entries/exits and no-trade decisions. Public calls do not supply this complete joined ground truth. Preserve source/timezone/translation uncertainty; freeze any interpretation before evaluating unseen sessions. No profitability or exact-reconstruction claim follows from this evidence.

## Safety and scope

Offline/read-only documentation only: `read_only=true`, `is_order_action=false`, `broker_api_called=false`, `allowed_for_live_execution=false`. PR #992 is untouched.
