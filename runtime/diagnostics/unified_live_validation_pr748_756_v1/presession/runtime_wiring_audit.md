# Runtime Wiring Audit - PR #763 Correction

Command:

```bash
rg -n "UNIFIED_LIVE_VALIDATION_PR748_756|AppendOnlyRecorder|unified_live_validation_pr748_756" run_live.sh main.py core scripts
```

Exit code: `0`

## Findings

- Enable variable consumed: only by `core/unified_live_validation_pr748_756/campaign_contract.py` and `scripts/run_unified_live_validation_pr748_756_v1.py`.
- Campaign identity loaded: only by campaign helper/launcher code, not by `main.py` or `run_live.sh`.
- Recorder instantiated: only by `core/unified_live_validation_pr748_756/launcher.py` and direct tests; not by the TradeBot runtime loop.
- Runtime events calling recorder: none proven from `main.py`, `run_live.sh`, or existing runtime modules.
- Shutdown sealing and audit: launcher-level sealing exists for supervised smoke evidence; TradeBot runtime shutdown does not invoke campaign sealing.
- Proposed `run_live.sh` process imports campaign module: no.

Verdict:

```text
CURRENT_LAUNCH_COMMAND_DOES_NOT_ACTIVATE_CAMPAIGN
BLOCKED_BY_RUNTIME_WIRING
```

## Raw rg Output

```text
scripts/run_unified_live_validation_pr748_756_v1.py:11:from core.unified_live_validation_pr748_756.campaign_contract import (
scripts/run_unified_live_validation_pr748_756_v1.py:19:from core.unified_live_validation_pr748_756.launcher import launch_runtime_child
scripts/run_unified_live_validation_pr748_756_v1.py:26:    needles = ("unified_live_validation_pr748_756", "UNIFIED_LIVE_VALIDATION_PR748_756")
scripts/run_unified_live_validation_pr748_756_v1.py:36:    parser.add_argument("--evidence-root", default="runtime/diagnostics/unified_live_validation_pr748_756_v1")
scripts/run_unified_live_validation_pr748_756_v1.py:77:        "launch_command": f"PYTHONPATH=. {ENABLE_ENV}=true python3 -B scripts/run_unified_live_validation_pr748_756_v1.py --origin-main-sha {args.origin_main_sha} --launch-live",
core/unified_live_validation_pr748_756/launcher.py:19:from core.unified_live_validation_pr748_756.campaign_contract import (
core/unified_live_validation_pr748_756/launcher.py:27:from core.unified_live_validation_pr748_756.recorder import AppendOnlyRecorder
core/unified_live_validation_pr748_756/launcher.py:28:from core.unified_live_validation_pr748_756.seal import seal_evidence_root
core/unified_live_validation_pr748_756/launcher.py:62:    recorder = AppendOnlyRecorder(identity)
core/unified_live_validation_pr748_756/recorder.py:9:from core.unified_live_validation_pr748_756.campaign_contract import CampaignIdentity, enrich_row
core/unified_live_validation_pr748_756/recorder.py:12:class AppendOnlyRecorder:
core/unified_live_validation_pr748_756/validators.py:9:from core.unified_live_validation_pr748_756.campaign_contract import READ_ONLY_FLAGS
core/unified_live_validation_pr748_756/campaign_contract.py:20:CAMPAIGN_NAME = "unified_live_validation_pr748_756_v1"
core/unified_live_validation_pr748_756/campaign_contract.py:21:ENABLE_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_ENABLE"
core/unified_live_validation_pr748_756/campaign_contract.py:22:RUN_ID_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_RUN_ID"
core/unified_live_validation_pr748_756/campaign_contract.py:23:EVIDENCE_ROOT_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_EVIDENCE_ROOT"
core/unified_live_validation_pr748_756/campaign_contract.py:24:COMPOSITION_SHA_ENV = "UNIFIED_LIVE_VALIDATION_PR748_756_COMPOSITION_SHA"

```
