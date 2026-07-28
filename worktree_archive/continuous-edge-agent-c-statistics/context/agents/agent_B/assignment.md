AGENT ID: agent_B
ROLE: Pipeline and temporal oracle
OBJECTIVE: Verify existing loaders, timestamp logic, session boundaries, next-bar entry, outcomes, MFE/MAE.
STARTING SHA: HEAD
WORKTREE: /Users/madhuram/.antigravity/worktrees/tradebot/continuous-edge-agent-b-oracle
BRANCH: research/continuous-structural-edge-discovery-v1
READ-ONLY OR WRITING: WRITING (to owned paths only)
OWNED FILES: research/continuous_structural_edge_discovery_v1/pipeline_audit/, research/continuous_structural_edge_discovery_v1/oracle/, tests/continuous_structural_edge_discovery_v1/oracle/
PROHIBITED FILES: production code, central context files
APPROVED INPUTS: 04_pipeline_authority.md
EXPECTED OUTPUTS: Handoff report and exact tests/commands.
REQUIRED COMMANDS: git status, git diff
REQUIRED TESTS: pytest tests/continuous_structural_edge_discovery_v1/oracle/
STOP CONDITIONS: context hash mismatch; missing approved source; scope conflict
HANDOFF FORMAT: handoff_template.md
MISSION HASH: ff3cc91f0bd55a7ed481faaadf0a7badeedbaf8d7f8f6f49abcd976bd78706d5
CONTRACT HASH: 919af5dc1d3ff962cdfd62533684c765460472c01a6c0cf280ca550d99c8309f
SAFETY HASH: 8444487476352c00349078b2a297e9f0d412c8469f4316cc844eef60b41e7f0d
