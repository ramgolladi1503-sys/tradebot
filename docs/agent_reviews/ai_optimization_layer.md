# Agent Work Contract
- source_agent: Antigravity
- action: ADD_AI_OPTIMIZATION_LAYER
- title: Add AI Optimization and CI/CD Verification Layer
- scope: Create .cursorignore, .cursorrules, scripts/verify_registry.py, and .github/workflows/verify-registry.yml.
- requested_paths: .cursorignore, .cursorrules, scripts/verify_registry.py, .github/workflows/verify-registry.yml
- allowed_paths: .cursorignore, .cursorrules, scripts/verify_registry.py, .github/workflows/verify-registry.yml
- forbidden_paths: core/, strategies/, runtime/
- expected_tests: None, CI verification script added instead
- acceptance_proof: CI passes and script exits 0 when all specs registered

# Scope Guard
This PR is tightly scoped to adding AI instructions and verification scaffolding. It does not touch runtime, execution, broker, or strategy code.

# Grill Me Review
CRITIQUE_SCOPE: Does this touch execution? No.
REVIEW_PR: Adds files for developer tools and CI only.
AUDIT_RISK: Zero risk to live trading.
FIND_FAKE_PROGRESS: This prevents future agents from creating fake progress by ignoring heavy files and mandating strategy registration.

# Hermes Review
DESIGN_ARCHITECTURE: Adds read-only checks for strategy registration and ignored directories.
DEFINE_CONTRACT: AI must write strictly asynchronous code and register strategies.
CREATE_ACCEPTANCE_GATES: GitHub Action runs `verify_registry.py`.

# GSD Review
PLAN_PR: Write 4 required files.
GENERATE_PATCH: Implemented.

# QA / Safety Review
read_only=true
is_order_action=false
broker_api_called=false
allowed_for_live_execution=false
append=false
mode=SIM
candidate_id=none
decision=pass
reason=setup-ci
timestamp=2026-06-14
source=antigravity

# Acceptance Proof
The verify_registry.py script runs successfully and exits with code 0 on the existing codebase.

# Runtime Proof Required After Merge
None.

# What This PR Does Not Prove
This does not prove that strategies are actually asynchronous, only that the rule is documented and strategies are registered.

# Human Approval
Approved explicitly by user request to add the optimization layer and verification script.
