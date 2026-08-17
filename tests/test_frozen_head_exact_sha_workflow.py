from pathlib import Path


WORKFLOW = Path(".github/workflows/frozen-head-exact-sha-certification.yml")


def test_base_authority_uses_event_base_or_dispatch_base_input():
    text = WORKFLOW.read_text()
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha || inputs.base_sha }}" in text
    assert "base_sha:" in text
    assert 'git fetch --no-tags origin "$BASE_SHA"' in text
    assert 'git diff --check "$BASE_SHA" "$HEAD_SHA"' in text


def test_non_main_workflow_does_not_derive_authority_from_origin_main():
    text = WORKFLOW.read_text()
    assert 'BASE_SHA="$(git rev-parse origin/main)"' not in text
    assert 'git diff --name-only origin/main' not in text


def test_candidate_is_not_executed_by_base_authority_jobs():
    text = WORKFLOW.read_text()
    assert "python scripts/validate_frozen_head_bridge.py" in text
    assert "python scripts/research/" not in text
