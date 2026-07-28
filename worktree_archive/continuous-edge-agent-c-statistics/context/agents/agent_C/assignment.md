AGENT ID: agent_C
ROLE: Statistics and controls infrastructure
OBJECTIVE: Build reusable evaluation and control infrastructure for a frozen candidate journal.
STARTING SHA: HEAD
WORKTREE: /Users/madhuram/.antigravity/worktrees/tradebot/continuous-edge-agent-c-statistics
BRANCH: research/continuous-structural-edge-discovery-v1
READ-ONLY OR WRITING: WRITING (to owned paths only)
OWNED FILES: research/continuous_structural_edge_discovery_v1/statistics/, research/continuous_structural_edge_discovery_v1/controls/, tests/continuous_structural_edge_discovery_v1/statistics/
PROHIBITED FILES: production code, unfrozen candidates, holdout outcomes
APPROVED INPUTS: 01_research_contract.md
EXPECTED OUTPUTS: Handoff report and exact tests/commands.
REQUIRED COMMANDS: git status, git diff
REQUIRED TESTS: pytest tests/continuous_structural_edge_discovery_v1/statistics/
STOP CONDITIONS: context hash mismatch; holdout access violation; scope conflict
HANDOFF FORMAT: handoff_template.md
MISSION HASH: ff3cc91f0bd55a7ed481faaadf0a7badeedbaf8d7f8f6f49abcd976bd78706d5
CONTRACT HASH: 919af5dc1d3ff962cdfd62533684c765460472c01a6c0cf280ca550d99c8309f
SAFETY HASH: 8444487476352c00349078b2a297e9f0d412c8469f4316cc844eef60b41e7f0d
