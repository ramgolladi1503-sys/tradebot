# Video Strategy: Independent Historical Analogue (Frozen Specification)

Status: independent research hypothesis, not OptionMate code or verified reproduction. Exact fidelity `NOT_MEASURABLE`.

## Evidence boundary and quantity semantics

The evidence register records short paraphrases from the Telugu recording's English machine translation. The translation may be inaccurate and caption authorship is unspecified. It supports discussion of five NIFTY spot levels (Trend Decider plus two reversal levels above/below), a broad RBFN mention, and nearby option-premium/strike selection including ₹38 and ₹68. The other cited amount is rendered ₹138 in one segment, not reliably ₹128. ₹28 and ₹158 are not confirmed in the cited video. User-provided ₹28/38/68/128/158 are premium-point scenario anchors only. They are not five spot levels or strike identifiers.

## Candidate functional decomposition

A generic Gaussian RBF candidate can map a causal feature vector `x` to reference outputs via `f(x)=b+Σ_j w_j exp(-||x-c_j||²/(2σ²))`. This formula only defines one possible model family; centers, width, normalization, training labels, output count, update cadence, and post-processing for OptionMate are unknown. The five-level chart description suggests an independent candidate with five ordered spot outputs, but exact construction is unknown. Do not claim midpoint-derived levels or any parameter as video fact.

Separate modules should represent (a) spot-level prediction, (b) price action around levels to infer CE/PE direction, (c) premium-anchor-to-contract selection using point-in-time option chain and expiry/strike/side identity, and (d) stops/targets. These module boundaries are testable design choices, not recovered internals. Keep spot levels, option premium prices, and strike IDs as different typed quantities.

## Frozen analogue parameters

Retain the previously frozen local research specification: train only on 2024–25 daily spot sessions; 28 deterministic RBF centers, width 3.4, ridge 4.0; six causal features and ordered low/close/high target outputs; form two additional midpoint levels as an explicit hypothesis. User anchors are evaluated independently. Candidate entries, premium tolerance, tie-breaks, stop cases, costs, and replay conventions remain local assumptions. They must not be retroactively described as OptionMate rules. No change to runner or results is authorized under this docs-only work item.

## Limits and decision

Local 2026 replay is incomplete-year, previously reused/contaminated, based on OHLC assumptions and conditional cost scenarios; it is not pristine out-of-sample certification or realized fills. Rights/lineage and exact OptionMate output joins remain unresolved. Verdict `NO-GO / RESEARCH-ONLY`; no live, paper, broker, or order authorization.
