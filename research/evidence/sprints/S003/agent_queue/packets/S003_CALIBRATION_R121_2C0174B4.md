# MROS S003 deterministic calibration R121

Repository: `ramgolladi1503-sys/tradebot`
Branch: `research/mros-program-v1`
Exact candidate HEAD: `2c0174b4becfc06a5db090d59944375693126ba1`

Run only this exact-head deterministic calibration command in the isolated Mac worker worktree:

```bash
/opt/anaconda3/bin/python3 scripts/mros/calibrate_review_audit_board_v2.py --candidate-head 2c0174b4becfc06a5db090d59944375693126ba1
```

Record Python version, exact command, complete stdout/stderr, exit code, and the final calibration verdict in the requested output artifact. Do not implement or repair anything in this job. Do not modify program state, sprint ledger, frozen gates, strategy/risk/execution/broker code, runtime authority, or M9. Runtime authority must remain `NONE`; broker actions must remain `NONE`.
