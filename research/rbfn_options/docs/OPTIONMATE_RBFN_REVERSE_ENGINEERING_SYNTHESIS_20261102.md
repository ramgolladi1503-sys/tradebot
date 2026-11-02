# OptionMate RBFN reverse-engineering synthesis — 2026-11-02

## Verdict

The recording supports a broad concept, not enough information to recover the exact function. Translated captions describe five NIFTY spot chart levels (Trend Decider and two reversal levels each side), name an RBFN family, and discuss corresponding strikes / nearby option-chain premiums. The Telugu-to-English machine translation may be inaccurate; caption authorship is unspecified. Exact OptionMate fidelity is `NOT_MEASURABLE`; verdict `NO-GO / RESEARCH-ONLY`.

## Keep the three layers distinct

1. **Spot layer:** a model produces or derives reference index levels. The video paraphrase supports five displayed levels, but not their formula, training labels, or exact values.
2. **Signal layer:** price behavior around Trend Decider/reversal levels suggests direction, continuation, or reversal and a CE/PE side. The translated discussion is discretionary; exact thresholds and state transitions are unknown.
3. **Contract layer:** the user identifies ₹28/₹38/₹68/₹128/₹158 as option-premium points and says strikes are selected with premiums around them. Translated captions support ₹38/₹68 and nearby-strike discussion; another amount appears as ₹138, so ₹128/₹138 remains unresolved. ₹28/₹158 are not verified in the cited video segments. These anchors are not strike IDs or spot levels.

## What an RBFN hypothesis can and cannot say

A Gaussian RBF candidate has a form such as `y(x)=b+Σ φ(||x-c_j||)w_j`, with `φ(r)=exp(-r²/(2σ²))`. This is only a generic model-family description. The recording does not establish the input feature vector, center selection, width, regularization, training set, target labels, refresh cadence, output count, or conversion into five levels. The local 28-center/3.4-width/ridge-4 model and its level construction are an independent research analogue, not recovered OptionMate parameters.

## Distinct research artefacts

Two local research threads must not be blended:

- The **premium-RBFN replay** is a separate strike-selection experiment using user premium anchors. Its outputs are local, conditional scenario analyses based on incomplete historical data and assumptions; prior variants reused the 2026 period.
- The **five-level video analogue** is a separate, independently specified hypothesis about spot reference levels and price behavior around them. No scenario from that analogue was preselected for reporting in this docs-only PR.

They differ in targets, selection rules, and evidence basis. Neither is a validated OptionMate implementation, and neither supplies ground truth for the other. Prior outputs remain available locally, but this documentation PR publishes no P&L: the option-source rights and processed-data lineage are unresolved, and no five-level analogue scenario was preselected. No reported figure here should be read as realized or executable net INR.

An independent future study could freeze the spot-level, signal, premium-anchor contract ranking, and exit components separately; compare against simple baselines; use only point-in-time chain data; and preserve no-trade/rejection dates. That would test a stated hypothesis, not establish that OptionMate uses those steps.

Evidence still needed: dated level vectors and generation times; associated index/instrument and exact option contract/expiry/strike/side; every entry, exit, rejection and no-trade; clarified anchor semantics including 128/138; rights-cleared quote/fill-quality data; a frozen mapping; untouched sessions; and independent replay review. Until then exact fidelity is `NOT_MEASURABLE` and the strategy verdict is `NO-GO / RESEARCH-ONLY`. No broker, order, paper, or live action is authorized.
