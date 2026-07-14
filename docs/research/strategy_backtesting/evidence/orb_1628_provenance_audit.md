# ORB 1628 provenance audit

Date: 2026-07-14
Worktree: `/Users/madhuram/.codex/worktrees/tradebot/orb-candle-validation`
Branch: `agent/codex-orb-candle-validation`
Current HEAD: `9be13b061e18310682365f932b044789c65ab577`

## Scope

This audit checks whether the historical `1628` candle-proxy result is reproducible from committed provenance rather than only from generated `/tmp` evidence.

The operative candle verdict remains:

`INVALID_DUE_TO_BACKTEST_HARNESS`

The strict option-replay verdict remains:

`INVALID_DUE_TO_DATA`

## `/tmp` provenance copy

The generated evidence bundle was found at:

- `/tmp/orb_candle_validation_results_corrected.json`

A safety copy was created at:

- `/tmp/tradebot-codex-orb-candle-validation/provenance/orb_candle_validation_results_corrected.json`

SHA-256 comparison:

- `/tmp/orb_candle_validation_results_corrected.json`: `132a8af1b32d6591accd7734ef6f25b107f0c60f56e3730cdbe8da0915710655`
- safety copy: `132a8af1b32d6591accd7734ef6f25b107f0c60f56e3730cdbe8da0915710655`

Classification: the copied artifact matches byte-for-byte.

## Provenance field audit

| element | status | evidence |
| --- | --- | --- |
| exact source root | PRESENT_AND_VERIFIABLE | `/Users/madhuram/tradebot/runtime/upstox_candidate_replay` in the docs; the `/tmp` bundle itself does not restate it |
| exact source files | MISSING | `/tmp` bundle only records `source_files: 60`, not the file paths |
| exact session dates | PRESENT_AND_VERIFIABLE | `per_session` contains 60 sessions; the docs enumerate the sampled dates |
| source-file hashes | NOT_RECORDED | only aggregate `raw_manifest_hash` is recorded |
| row counts | PRESENT_AND_VERIFIABLE | `rows: 22500` |
| instrument filters | PRESENT_AND_VERIFIABLE | corpus is NIFTY-only in the docs; the `/tmp` bundle does not re-list the raw files |
| date filters | PRESENT_AND_VERIFIABLE | 60-session sampled corpus described in the docs |
| preparation functions | PRESENT_AND_VERIFIABLE | `scripts/backtest_all_strategies_available_data.py::_prepare_frames`, `_market_row`, `_proxy_trade_rows` in the docs |
| prepared-frame schema | PRESENT_BUT_AMBIGUOUS | the docs describe the prepared shape, but the `/tmp` bundle does not serialize the frame schema |
| prepared-input hash | PRESENT_AND_VERIFIABLE | `89b5423b1f003dd729ca90d8e8373479f76ad79527b1aa480230cc300bca8ab7` |
| candidate-generation configuration | PRESENT_BUT_AMBIGUOUS | candidate hash/count are recorded, but the exact CLI/config invocation is not recorded in `/tmp` |
| ORB thresholds | PRESENT_BUT_AMBIGUOUS | the docs describe the strategy thresholds; the `/tmp` bundle does not record the active threshold set explicitly |
| holding horizon | PRESENT_AND_VERIFIABLE | `maximum_trade_duration_minutes: 15`, `maximum_trade_bars: 15` |
| friction settings | PRESENT_AND_VERIFIABLE | baseline/adverse/severe are recorded in the bundle |
| WFA settings | PRESENT_BUT_AMBIGUOUS | WFA trade count and hashes are recorded, but fold parameters are not fully serialized in `/tmp` |
| candidate hash | PRESENT_AND_VERIFIABLE | `c4b8375a1312b7ce2f2cf3a18f472392fcdb176183d5b34a68d5b697fd1646b5` |
| trade hash | PRESENT_AND_VERIFIABLE | `2122c7512465850a1769ef85abe37fcdf32b8cd47657017ab4097ffe230c3d38` |
| command or script identity | NOT_RECORDED | no CLI command is stored in the `/tmp` JSON |
| code commit | NOT_RECORDED | no commit SHA is stored in the `/tmp` JSON |
| working directory | NOT_RECORDED | no working directory is stored in the `/tmp` JSON |
| Python executable | NOT_RECORDED | not stored in the `/tmp` JSON |
| environment variables | NOT_RECORDED | not stored in the `/tmp` JSON |
| generated timestamps | NOT_RECORDED | not stored in the `/tmp` JSON |
| output paths | PRESENT_BUT_AMBIGUOUS | the bundle exists under `/tmp`, but the command that wrote it is not recorded |

## Search for the original prepared-input mechanism

What was recoverable:

- The current harness code in `scripts/backtest_all_strategies_available_data.py` is committed and identical across the source and Codex worktrees.
- The source branch contains the session-safe harness fix (`d9c34187bd0146dc5bb4a034434d4e89efd7259c`).
- The `/tmp` artifact captures the canonical hashes used in the docs.
- The `/tmp` bundle shows 60 sampled sessions and 22,500 rows.

What was not recoverable from committed provenance:

- the exact file list used to construct the 60-session corpus
- the exact command or script invocation that wrote the canonical bundle
- the exact prepared-frame schema used when the bundle was generated
- any durable, committed manifest that maps source file paths to the canonical hashes

Classification: `STALE_DOCUMENTED_RESULT_WITHOUT_REPRODUCIBLE_PROVENANCE`

## Interpretation

The 1628 result is still a valid generated artifact for traceability, but it is not reproducible from committed evidence in this checkout.

That means:

- the number is not a stable canonical result
- the docs must not present it as final executable ORB truth
- the operative candle verdict stays `INVALID_DUE_TO_BACKTEST_HARNESS`
- the strict replay lane stays `INVALID_DUE_TO_DATA`

## Required separation from semantic defects

Even if the 1628 result had been reproducible, it would still be a candle proxy result only.

It would not resolve:

- ATR-derived `vol_z` semantics being mapped through `volume_z`
- same-candle-close proxy execution
- missing production position semantics
- lack of explicit rejected-candidate objects

## Conclusion

The `1628` historical claim is withdrawn as an operative result because the exact provenance needed to reconstruct it is missing from committed artifacts.

The only safe classification is:

`STALE_DOCUMENTED_RESULT_WITHOUT_REPRODUCIBLE_PROVENANCE`
