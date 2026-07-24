# Worktree Supervisor Main V2

## Scope

- Branch: `feat/worktree-supervisor-main-v2`
- Base: `origin/main` at `a48176fc245375f15e316493364915ec37439e29`
- Worktree: `/Users/madhuram/tradebot-worktree-supervisor-main-v2`
- Historical reference only: `origin/agent/tradebot-worktree-supervisor`
- Purpose: selectively integrate local agent worktree supervision without merging historical branch history.

## Change

- Adds a local worktree-supervisor facade, contract model, claim registry, evidence manifests, and CLI.
- Integrates with current-main owners by calling:
  - `core.agent_work_contract.normalize_agent_work_request`
  - `core.agent_work_contract.validate_agent_work_contract`
  - `core.agent_scope_guard.assess_agent_scope`
  - `core.agent_approval.approve_agent_scope`
- Fails closed with `TRADEBOT_SCOPE_GUARD_UNAVAILABLE` if the current-main guard chain cannot be loaded.
- Runs acceptance commands only in a detached, credential-isolated git worktree with isolated HOME and blocked broker/secret environment fragments.
- Requires independent reviewer evidence before normal release.

## Safety Boundaries

- Broker APIs called: `NO`
- Order actions placed/modified/cancelled: `NO`
- Runtime live configuration changed: `NO`
- Strategy thresholds changed: `NO`
- WFA, parameter search, or production strategy execution run: `NO`
- Audit worktree runtime files touched: `NO`
- Research data or runtime parquet artifacts staged: `NO`
- Auto-merge behavior added: `NO`

## Evidence

- `pytest -q tests/test_agent_supervisor.py`: `16 passed`
- `pytest -q tests/test_agent_work_contract.py tests/test_agent_scope_guard.py tests/test_agent_approval.py tests/test_submit_agent_work.py tests/test_agent_contracts.py`: `41 passed`
- `python3 -m py_compile core/agent_supervisor.py core/agent_supervisor_claims.py core/agent_supervisor_contract.py core/agent_supervisor_evidence.py core/agent_supervisor_git.py core/agent_supervisor_types.py scripts/agent_supervisor.py tests/test_agent_supervisor.py`: passed
- `ruff check core/agent_supervisor.py core/agent_supervisor_claims.py core/agent_supervisor_contract.py core/agent_supervisor_evidence.py core/agent_supervisor_git.py core/agent_supervisor_types.py scripts/agent_supervisor.py tests/test_agent_supervisor.py`: passed
- `git diff --check`: passed

## Notes

- The implementation was reconstructed file-by-file from the historical reference branch and adapted only where current-main validation exposed drift.
- The macOS `/var` versus `/private/var` checkout path is resolved before setting sandbox `PYTHONPATH`, preserving the credential-isolation assertion.
