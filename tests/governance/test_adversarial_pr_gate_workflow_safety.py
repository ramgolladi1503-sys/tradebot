from pathlib import Path


WORKFLOW = Path(".github/workflows/adversarial-pr-gate.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_attack_workflow_pins_candidate_to_exact_head_and_base():
    text = _workflow_text()
    candidate = text.split("candidate-adversarial-execution:", 1)[1].split(
        "trusted-adversarial-policy:", 1
    )[0]
    assert "ref: ${{ github.event.pull_request.head.sha }}" in candidate
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in candidate
    assert 'BASE_SHA: ${{ github.event.pull_request.base.sha }}' in candidate
    assert 'test "$(git rev-parse HEAD)" = "$HEAD_SHA"' in candidate
    assert "persist-credentials: false" in candidate


def test_attack_workflow_gives_candidate_no_write_permissions():
    text = _workflow_text()
    candidate = text.split("candidate-adversarial-execution:", 1)[1].split(
        "trusted-adversarial-policy:", 1
    )[0]
    assert "permissions:\n      contents: read" in candidate
    assert "statuses: write" not in candidate
    assert "pull-requests: write" not in candidate
    assert "contents: write" not in candidate


def test_trusted_policy_uses_protected_main_and_never_checks_out_candidate():
    text = _workflow_text()
    trusted = text.split("trusted-adversarial-policy:", 1)[1]
    assert "ref: main" in trusted
    assert "persist-credentials: false" in trusted
    assert "statuses: write" in trusted
    assert "ref: ${{ github.event.pull_request.head.sha }}" not in trusted
    assert "git checkout" not in trusted
    assert "git switch" not in trusted


def test_trusted_policy_publishes_exact_head_verdict_context():
    text = _workflow_text()
    trusted = text.split("trusted-adversarial-policy:", 1)[1]
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in trusted
    assert '"context":"adversarial-pr-trusted-head"' in trusted
    assert '"https://api.github.com/repos/$REPOSITORY/statuses/$HEAD_SHA"' in trusted
    assert "if: always()" in trusted
    assert "steps.trusted_policy.outcome != 'success'" in trusted


def test_trusted_policy_does_not_install_or_execute_candidate_dependencies():
    text = _workflow_text()
    trusted = text.split("trusted-adversarial-policy:", 1)[1]
    assert "pip install" not in trusted
    assert "requirements.txt" not in trusted
    assert "refs/remotes/origin/pr-${{ github.event.pull_request.number }}-head" in trusted


def test_workflow_defaults_to_no_permissions_and_scopes_write_to_trusted_job():
    text = _workflow_text()
    pre_jobs = text.split("jobs:", 1)[0]
    assert "permissions: {}" in pre_jobs
    assert text.count("statuses: write") == 1
