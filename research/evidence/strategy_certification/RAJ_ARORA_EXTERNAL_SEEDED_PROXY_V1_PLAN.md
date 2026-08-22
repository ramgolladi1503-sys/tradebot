# Raj Arora External-Seeded Intraday Proxy V1

Status: `FROZEN_PRE_DEVELOPMENT`

This is a research-only external hypothesis replication lane. It does **not** claim that the proxy rules below are the exact strategy described by Raj Arora in the linked video. The exact strategy transcript was not available to this research run, so the source is used only as a seed for a small, predeclared family of plausible opening-auction mechanisms.

## Authority

- Branch: `research/raj-arora-external-seeded-proxy-v1`
- Parent: `research/strategy-certification-kernel-v0`
- Runtime authority: `NONE`
- Broker actions permitted: `false`
- Dataset: frozen NIFTY canonical 5-minute corpus
- Expected rows: `36,849`
- Expected sessions: `493`
- Dataset SHA-256: `6a145d4d17f124f9dc8ee272c5a19ca98988873a14b294765f44a27284d8b7e8`
- Chronological split: `295 development / 98 validation / 100 holdout`
- Development base round-trip cost: `2 bps`
- Development minimum trades: `50`
- Development horizons: `1 / 3 / 6` five-minute bars
- Validation and holdout are forbidden during the first screen.

## Frozen family

### 1. Opening-range breakout -> retest -> continuation

Opening range uses the first `10 / 15 / 30` minutes. A completed close must break the range with either `0` or `5 bps` buffer. A later bar must retest and hold the broken boundary within three bars. A separate later bar must confirm continuation through the retest-bar extreme within two bars.

### 2. Opening-range failed breakout -> reversal

The same frozen opening-range choices are used. A completed close breaks the opening range with `0` or `5 bps` buffer, then a later completed close returns inside the opening range within two bars. Direction is opposite the failed breakout.

### 3. Opening drive -> orderly pullback -> resumption

The first `10 / 15 / 30` minutes must produce a directional opening drive of at least `15 / 25 bps`. A later countertrend pullback must retrace `25-65%` of that drive without erasing its origin. A separate later bar must resume through the pullback extreme within two bars.

Total frozen development search budget: `18 signal configurations x 3 horizons = 54 cells`.

## Why the family is deliberately small

The prior 5-minute price-only and cross-market price-only hunts are closed negative search domains. This lane is not permission to restart arbitrary price-threshold mining. It is a bounded external-hypothesis replication experiment. No extension of this grid is permitted after results are observed. Any material rule change is a new generation and a new multiple-testing family.

## Data limitations

Do not add volume, VWAP, bid/ask, spread, OI, option-chain, or executable option-P&L conditions to this V1. The frozen 493-session canonical underlying corpus does not provide independently usable historical liquidity/option-execution fields for those claims. Richer-data versions require a separately certified information set.

## Development command

```bash
cd /Users/madhuram/tradebot-strategy-certification-kernel-v0

git fetch origin
git checkout research/raj-arora-external-seeded-proxy-v1

python3 -m pytest --confcutdir=tests/research \
  tests/research/test_raj_arora_external_seeded_proxy_v1.py -q

python3 -u scripts/research/hypothesis_factory/run_raj_arora_external_seeded_proxy_v1_development.py \
  --repo-root .
```

Expected output:

`research/evidence/strategy_certification/RAJ_ARORA_EXTERNAL_SEEDED_PROXY_V1_DEVELOPMENT.json`

The runner verifies the exact dataset SHA, row count and session count before computing anything. It reads development sessions only. If no configuration has at least 50 development trades and positive mean net return after the frozen 2 bps cost, the V1 family closes with no development survivor.

If a development survivor exists, freeze that exact nomination first. Before validation, run the predeclared cost, entry-delay, parameter-neighborhood, randomized-direction, session-permutation and regime-stability controls. Do not tune using validation. Do not access holdout unless the frozen candidate passes validation and the required robustness controls.
