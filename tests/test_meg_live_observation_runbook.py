from pathlib import Path


def test_runbook_does_not_require_fabricated_pr786_cli():
    text = (Path(__file__).parents[1] / "docs/runbooks/meg_live_observation_readiness_v1.md").read_text()
    assert "no `POSTMARKET_786_VERIFY_COMMAND` is valid" in text
    assert "run_ai_reliability_pr763_session.py" in text
    assert "assemble_meg_shadow_system_certificate.py" in text
    assert "ONE_SESSION_ROOT" in text
