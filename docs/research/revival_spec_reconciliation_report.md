# Revival Candidates Specification Reconciliation Report

Date: 2026-09-22
Reviewer: GSD Stage 2 Execution
Governing Document: `AGENTS.md` / `output/revival_candidate_freeze_manifests_20260922.json`

## Candidate Reconciliation Summary

| Candidate ID | Name | Source Artifact | Reconciliation Status |
|---|---|---|---|
| `CAND_01_SESSION_DIR_OVERNIGHT` | Session-direction -> overnight persistence | `output/SESSION_DIRECTION_OVERNIGHT_SELECTION_FREEZE_20260922.md` | `RECONCILED_FOR_PROSPECTIVE_SHADOW` |
| `CAND_02_GAP_DIR_CONFLUENCE_A` | Delayed direction / gap confluence A | `output/GAP_DIRECTION_CONFLUENCE_DELAYED_ENTRY_SELECTION_FREEZE_20260922.md` | `RECONCILED_FOR_PROSPECTIVE_SHADOW` |
| `CAND_03_DAY_NIGHT_MOMENTUM` | Day-to-night momentum +/-50 | `output/day_to_night_momentum_reconciled_candidate_20260921.md` | `RECONCILED_FOR_PROSPECTIVE_SHADOW` |
| `CAND_04_LOW_GAP_LOW_PRIOR_RET` | Low gap x low prior return | `output/frozen_holdout_gap_prior_return_20260921.md` | `RECONCILED_FOR_PROSPECTIVE_SHADOW` |
| `CAND_05_DAY_NIGHT_OI_CONFIRM` | Day-to-night OI confirmation | `output/day_to_night_oi_confirmation_candidate_20260921.md` | `BLOCKED_RECONCILIATION_REQUIRED` |
| `CAND_06_GAP_CONFLUENCE_RANGE_EXP_B` | Gap confluence + range expansion B | `output/gap_confluence_prior_range_expansion_replication_20260922.md` | `BLOCKED_RECONCILIATION_REQUIRED` |

## Detailed Findings

### 1. Reconciled Candidates (Queue 1 Ready)

1. **CAND_01_SESSION_DIR_OVERNIGHT**:
   - Recovered exact parameter-free rule from `SESSION_DIRECTION_OVERNIGHT_SELECTION_FREEZE_20260922.md`.
   - Direction: `D = close_15:29 - open_09:15`. Entry: next session 09:15 open. Gap outcome: `direction * (open_next - close_15:29)`.
   - Artifact SHA verified on disk: `4ad7418493c1ec4af5197d3b169bf1007863e09263c125d2101b3a0fbd2d595e`.
   - Canonical Parquet SHA: `829f2e72ab3e97b8a9262cee741f738ac62a37d2634fe108886648ff125ffec9`.
   - Prospective Start Boundary: `2026-09-22T00:00:00+05:30`.

2. **CAND_02_GAP_DIR_CONFLUENCE_A**:
   - Recovered exact rule from `GAP_DIRECTION_CONFLUENCE_DELAYED_ENTRY_SELECTION_FREEZE_20260922.md`.
   - Confluence: `sign(prior 15:29 close - prior 09:15 open) == sign(current 09:15 open - prior 15:29 close)`.
   - Entry: 09:20 close, Exit: 10:15 close.
   - Artifact SHA: `c4c42df02462acc7e1ecbfd714b586a595e28f24d23f2d8e3a43c533228bb30d`.

3. **CAND_03_DAY_NIGHT_MOMENTUM**:
   - Recovered exact rule from `day_to_night_momentum_reconciled_candidate_20260921.md`.
   - Move: `Rday = close_15:25 - open_09:15`. Emitted only when `|Rday| > 50.0` points.
   - Entry: next session 09:16 futures open with verified unchanged contract key.
   - Artifact SHA: `7a8e2445a3bb8327cf0876e1fa4a9ac05b8d9d5967df2b077febc98b8ce8a567`.

4. **CAND_04_LOW_GAP_LOW_PRIOR_RET**:
   - Recovered exact rule from `frozen_holdout_gap_prior_return_20260921.md`.
   - Overnight gap < -17.04 bps and prior session open-to-close < -69.30 bps.
   - Entry: 09:15 open, Exit: 11:30 close.
   - Artifact SHA: `b6f47e9fb185d4d8cae539bbf80bc043db875f7ccbe739249e4d9e43b4d141f6`.

### 2. Blocked Candidates (Fail-Closed)

5. **CAND_05_DAY_NIGHT_OI_CONFIRM**:
   - Status: `BLOCKED_RECONCILIATION_REQUIRED`.
   - Blocker: Declared in prose as requiring a prospective audit, but lacks a machine-readable `SELECTION_FREEZE` artifact with exact numerical OI delta threshold and contract-roll handling.

6. **CAND_06_GAP_CONFLUENCE_RANGE_EXP_B**:
   - Status: `BLOCKED_RECONCILIATION_REQUIRED`.
   - Blocker: Existing research explicitly notes late-half failure (-5.62 pts) and states "The current late-half failure prevents certification; the branch remains watchlist-only requiring independent freeze/reproduction." No machine-readable freeze document exists.
