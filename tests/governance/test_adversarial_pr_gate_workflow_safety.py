from pathlib import Path


WORKFLOW = Path(".github/workflows/adversarial-pr-gate.yml")


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _candidate_job(text: str) -> str:
    return text.split("candidate-adversarial-execution:", 1)[1].split(
        "trusted-adversarial-policy:", 1
    )[0]


def _trusted_job(text: str) -> str:
    return text.split("trusted-adversarial-policy:", 1)[1]


def test_attack_workflow_pins_candidate_to_exact_head_and_base():
    candidate = _candidate_job(_workflow_text())
    assert "ref: ${{ github.event.pull_request.head.sha }}" in candidate
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in candidate
    assert 'BASE_SHA: ${{ github.event.pull_request.base.sha }}' in candidate
    assert 'test "$(git rev-parse HEAD)" = "$HEAD_SHA"' in candidate
    assert "persist-credentials: false" in candidate


def test_attack_workflow_gives_candidate_no_write_permissions():
    candidate = _candidate_job(_workflow_text())
    assert "permissions:\n      contents: read" in candidate
    assert "statuses: write" not in candidate
    assert "pull-requests: write" not in candidate
    assert "contents: write" not in candidate


def test_pinned_python_precedes_static_inspection_and_dependency_install():
    candidate = _candidate_job(_workflow_text())
    setup_pos = candidate.index("Set up trusted Python runtime")
    inspect_pos = candidate.index("Static adversarial inspection before dependency installation")
    install_pos = candidate.index("Install trusted-base test dependencies")
    test_pos = candidate.index("Execute changed tests under adversarial gate")
    assert setup_pos < inspect_pos < install_pos < test_pos
    assert 'python-version: "3.12"' in candidate


def test_candidate_installs_only_base_requirements_not_candidate_requirements():
    candidate = _candidate_job(_workflow_text())
    assert "git show refs/remotes/origin/adversarial-base:requirements.txt" in candidate
    assert "pip install -r /tmp/adversarial-base-requirements.txt" in candidate
    assert "pip install -r requirements.txt" not in candidate
    assert 'cache: "pip"' not in candidate


def test_trusted_policy_uses_protected_main_and_never_checks_out_candidate():
    trusted = _trusted_job(_workflow_text())
    assert "ref: main" in trusted
    assert "persist-credentials: false" in trusted
    assert "statuses: write" in trusted
    assert "ref: ${{ github.event.pull_request.head.sha }}" not in trusted
    assert "git checkout" not in trusted
    assert "git switch" not in trusted


def test_trusted_policy_publishes_exact_head_verdict_context():
    trusted = _trusted_job(_workflow_text())
    assert 'HEAD_SHA: ${{ github.event.pull_request.head.sha }}' in trusted
    assert '"context":"adversarial-pr-trusted-head"' in trusted
    assert '"https://api.github.com/repos/$REPOSITORY/statuses/$HEAD_SHA"' in trusted
    assert "if: always()" in trusted
    assert "steps.trusted_policy.outcome != 'success'" in trusted


def test_trusted_policy_does_not_install_or_execute_candidate_dependencies():
    trusted = _trusted_job(_workflow_text())
    assert "pip install" not in trusted
    assert "requirements.txt" not in trusted
    assert "refs/remotes/origin/pr-${{ github.event.pull_request.number }}-head" in trusted


def test_workflow_defaults_to_no_permissions_and_scopes_write_to_trusted_job():
    text = _workflow_text()
    pre_jobs = text.split("jobs:", 1)[0]
    assert "permissions: {}" in pre_jobs
    assert text.count("statuses: write") == 1


def test_workflow_rechecks_when_pr_metadata_or_base_target_is_edited():
    text = _workflow_text()
    header = text.split("permissions:", 1)[0]
    assert header.count("edited") == 2
    assert "synchronize" in header
    assert "reopened" in header
