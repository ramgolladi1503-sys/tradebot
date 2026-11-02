# Video Strategy: Independent Historical Analogue (Frozen Specification)

Status: independent research hypothesis, not OptionMate code or verified reproduction. Exact fidelity `NOT_MEASURABLE`.

## Evidence boundary and quantity semantics

The evidence register records short paraphrases from the Telugu recording's English machine translation and direct playback review of English auto-captions on 2026-11-03. Translation/caption accuracy and authorship are uncertain. The 4:31 caption's four-prices/five wording is ambiguous; around 4:40, a NIFTY 50 Index chart visibly shows “Reversal Price” and “Trend Decider Price” overlays. This supports chart/spot classification, but not an exact overlay count. Later captions narrowly mention option-chain values 38 and 68, an unclear third value, and selecting a strike. The 6:11 caption renders unqualified 138; its meaning, unit/currency and relation are unknown, with no supported link to the user's clarification or later option-chain discussion. The user's clarification that RBFN-derived premium values ₹28/38/68/128/158 precede nearby-strike selection remains USER_CLARIFICATION, not source-verified. The early chart overlays are distinct from later premium-chain examples; no evidence connects them or establishes the five values as model outputs. These values are not static user-defined targets in the user's described method or strike identifiers.

## Candidate functional decomposition

A generic Gaussian RBF candidate can map a causal feature vector `x` to reference outputs via `f(x)=b+Σ_j w_j exp(-||x-c_j||²/(2σ²))`. This formula only defines one possible model family; centers, width, normalization, training labels, output count, update cadence, and post-processing for OptionMate are unknown. The chart overlays suggest an independent candidate with multiple spot outputs, but the exact count and construction are unknown. Do not claim midpoint-derived levels or any parameter as video fact.

Separate modules should represent (a) spot-level prediction, (b) price action around levels to infer CE/PE direction, (c) premium-anchor-to-contract selection using point-in-time option chain and expiry/strike/side identity, and (d) stops/targets. These module boundaries are testable design choices, not recovered internals. Keep spot levels, option premium prices, and strike IDs as different typed quantities.

## Frozen analogue parameters

Retain the previously frozen local research specification: train only on 2024–25 daily spot sessions; 28 deterministic RBF centers, width 3.4, ridge 4.0; six causal features and ordered low/close/high target outputs; form two additional midpoint levels as an explicit hypothesis. Separately, this analogue's fixed premium-value scenario inputs are local experimental choices; they do not implement the user's clarification that the RBFN derives premium values before nearby-strike selection. Candidate entries, premium tolerance, tie-breaks, stop cases, costs, and replay conventions remain local assumptions. They must not be retroactively described as OptionMate rules. No change to runner or results is authorized under this docs-only work item.

## Limits and decision

Local 2026 replay is incomplete-year, previously reused/contaminated, based on OHLC assumptions and conditional cost scenarios; it is not pristine out-of-sample certification or realized fills. Rights/lineage and exact OptionMate output joins remain unresolved. Verdict `NO-GO / RESEARCH-ONLY`; no live, paper, broker, or order authorization.
