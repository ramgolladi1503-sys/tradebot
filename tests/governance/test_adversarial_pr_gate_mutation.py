from scripts import run_adversarial_pr_gate as gate


def test_mutation_removing_all_tests_is_detected():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE" in errors
    assert "HIGH_RISK_CHANGE_WITHOUT_MUTATION_TEST_FILE" in errors


def test_mutation_replacing_negative_test_with_happy_path_is_detected(monkeypatch):
    source = "\n".join(
        [
            "import core.risk_guard",
            "",
            "def test_success_path_one():",
            "    assert allowed is True",
            "",
            "def test_success_path_two():",
            "    assert allowed is True",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_risk_guard_mutation.py"],
        errors,
    )
    assert any(e.startswith("ADVERSARIAL_NEGATIVE_CASE_FLOOR_FAIL") for e in errors)


def test_mutation_unreachable_assertions_do_not_satisfy_attack_floor(monkeypatch):
    source = "\n".join(
        [
            "import core.risk_guard",
            "",
            "def test_attack_invalid_one():",
            "    if False:",
            "        assert rejected is True",
            "",
            "def test_attack_invalid_two():",
            "    return",
            "    assert rejected is True",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_risk_guard_mutation.py"],
        errors,
    )
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_mutation_aliasing_eval_is_detected_by_ast_delta(monkeypatch):
    base = "def safe():\n    return 1\n"
    candidate = "def unsafe():\n    runner = eval\n    return runner('1+1')\n"
    monkeypatch.setattr(gate, "_read_ref", lambda ref, path: base)
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: candidate)
    monkeypatch.setattr(gate, "changed_diff", lambda base_ref, candidate_ref, path: "")
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert any("DANGEROUS_API_AST_DELTA:core/foo.py:name:eval" in e for e in errors)


def test_mutation_multiline_compile_is_detected_by_ast_delta(monkeypatch):
    base = "def safe():\n    return 1\n"
    candidate = "def unsafe():\n    return compile(\n        'x=1',\n        '<x>',\n        'exec',\n    )\n"
    monkeypatch.setattr(gate, "_read_ref", lambda ref, path: base)
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: candidate)
    monkeypatch.setattr(gate, "changed_diff", lambda base_ref, candidate_ref, path: "")
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert any("DANGEROUS_API_AST_DELTA:core/foo.py:name:compile" in e for e in errors)


def test_mutation_gate_edit_without_trusted_exact_sha_authority_is_detected(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    monkeypatch.setattr(gate, "_trusted_recertification_authorized", lambda base, candidate: False)
    errors = []
    gate._governance_self_protection(
        "base",
        ["scripts/run_adversarial_pr_gate.py"],
        "governance/adversarial-gate-recertification-v99",
        errors,
        "candidate",
    )
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED")
