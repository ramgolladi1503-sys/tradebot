from scripts import run_adversarial_pr_gate as gate


PROTECTED = ["scripts/run_adversarial_pr_gate.py"]
RECERT_BRANCH = "governance/adversarial-gate-recertification-v2"


def test_recertification_branch_name_alone_cannot_modify_gate(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    monkeypatch.setattr(gate, "_trusted_recertification_authorized", lambda base, candidate: False)
    errors = []
    gate._governance_self_protection("base", PROTECTED, RECERT_BRANCH, errors, "candidate")
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED")


def test_exact_sha_trusted_manifest_can_authorize_recertification(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    monkeypatch.setattr(gate, "_trusted_recertification_authorized", lambda base, candidate: True)
    errors = []
    gate._governance_self_protection("base", PROTECTED, RECERT_BRANCH, errors, "candidate")
    assert errors == []


def test_authorization_does_not_apply_to_ordinary_feature_branch(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    monkeypatch.setattr(gate, "_trusted_recertification_authorized", lambda base, candidate: True)
    errors = []
    gate._governance_self_protection(
        "base", PROTECTED, "feature/not-a-recertification", errors, "candidate"
    )
    assert errors


def test_manifest_requires_exact_lines_not_substrings(monkeypatch):
    candidate_sha = "a" * 40
    monkeypatch.setattr(gate, "_git", lambda *args: candidate_sha)

    class Result:
        returncode = 0

        def __init__(self, text):
            self.stdout = text

    malformed = (
        f"candidate_sha: {candidate_sha}\nscope: adversarial-gate-recertification\n",
        f"candidate_sha: {'b' * 40}\nauthorized: true\nscope: adversarial-gate-recertification\n",
        f"candidate_sha: {candidate_sha}\nauthorized: true\nscope: something-else\n",
        f"candidate_sha: {candidate_sha}\nauthorized: true-but-no\nscope: adversarial-gate-recertification\n",
        f"candidate_sha: {candidate_sha}\nauthorized: true\nscope: adversarial-gate-recertification-extra\n",
        f"candidate_sha: {candidate_sha}-suffix\nauthorized: true\nscope: adversarial-gate-recertification\n",
    )
    for text in malformed:
        monkeypatch.setattr(gate, "_run", lambda args, check=False, value=text: Result(value))
        assert gate._trusted_recertification_authorized("base", "candidate") is False


def test_manifest_with_exact_candidate_sha_scope_and_authority_is_accepted(monkeypatch):
    candidate_sha = "a" * 40
    monkeypatch.setattr(gate, "_git", lambda *args: candidate_sha)

    class Result:
        returncode = 0
        stdout = (
            f"candidate_sha: {candidate_sha}\n"
            "authorized: true\n"
            "scope: adversarial-gate-recertification\n"
        )

    monkeypatch.setattr(gate, "_run", lambda args, check=False: Result())
    assert gate._trusted_recertification_authorized("base", "candidate") is True
