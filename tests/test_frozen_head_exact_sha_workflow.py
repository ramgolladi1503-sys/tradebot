from pathlib import Path


WORKFLOW = Path(".github/workflows/frozen-head-exact-sha-certification.yml")
VALIDATOR = Path("scripts/validate_frozen_head_bridge.py")


def test_base_authority_uses_pull_request_event_base_only():
    text = WORKFLOW.read_text()
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in text
    assert "inputs." not in text
    assert "workflow_dispatch:" not in text
    assert "pull_request_target:" in text
    assert "branches: [main]" in text
    assert "types: [opened, reopened, synchronize, ready_for_review, edited]" in text
    assert "trusted-evidence-coverage:" in text
    trusted_job = text.split("  trusted-evidence-coverage:", 1)[1]
    trusted_condition = next(
        line.strip() for line in trusted_job.splitlines()
        if line.strip().startswith("if:")
    )
    assert trusted_condition.startswith(
        "if: ${{ github.event_name == 'pull_request_target' "
        "&& github.event.pull_request.base.ref == 'main' && !("
    )
    assert "github.event.action == 'edited'" in trusted_condition
    assert "!contains(toJSON(github.event.changes), '\"base\"')" in trusted_condition
    assert "contains(toJSON(github.event.changes), '\"title\"')" in trusted_condition
    assert "contains(toJSON(github.event.changes), '\"body\"')" in trusted_condition
    for job in (
        "exact-sha-identity",
        "agent-review-base-authority",
        "runtime-authority-base-authority",
        "code-excellence-base-authority",
        "trusted-evidence-coverage",
    ):
        assert f"  {job}:" in text
    assert "permissions:\n  contents: read\n  pull-requests: read" in text
    assert "    permissions:\n      contents: read" in text
    assert 'git fetch --no-tags origin "$BASE_SHA"' in text
    assert 'git diff --check "$BASE_SHA" "$HEAD_SHA"' in text


def test_non_main_workflow_does_not_derive_authority_from_origin_main():
    text = WORKFLOW.read_text()
    assert 'BASE_SHA="$(git rev-parse origin/main)"' not in text
    assert 'git diff --name-only origin/main' not in text


def test_validator_uses_explicit_base_sha_not_origin_main():
    text = VALIDATOR.read_text()
    assert 'base = git("rev-parse", args.base_sha)' in text
    assert 'actual_base = git("rev-parse", "origin/main")' not in text
    assert "BASE_SHA_DRIFT" not in text
    assert 'merge_base = git("merge-base", base, candidate)' in text
    assert 'print(f"PR_BASE_SHA={base}")' in text


def test_candidate_is_not_executed_by_base_authority_jobs():
    text = WORKFLOW.read_text()
    assert "python scripts/validate_frozen_head_bridge.py" in text
    assert "python scripts/research/" not in text
