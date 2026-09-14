from scripts import run_adversarial_pr_gate as gate


def test_high_risk_classification_covers_execution_risk_and_strategies():
    assert gate._high_risk("main.py")
    assert gate._high_risk("core/execution_engine.py")
    assert gate._high_risk("core/risk_engine.py")
    assert gate._high_risk("core/feed/supervisor.py")
    assert gate._high_risk("strategies/foo.py")
    assert not gate._high_risk("docs/readme.md")


def test_production_change_without_test_change_fails():
    errors = []
    gate._coverage_shape_attack(["core/foo.py"], errors)
    assert "PRODUCTION_CHANGE_WITHOUT_TEST_CHANGE" in errors


def test_high_risk_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(
        ["core/risk_guard.py", "tests/test_risk_guard.py"],
        errors,
    )
    assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_high_risk_change_accepts_mutation_or_safety_test_name():
    for test_path in (
        "tests/test_risk_guard_mutation.py",
        "tests/test_risk_guard_safety.py",
        "tests/test_risk_guard_adversarial.py",
        "tests/test_risk_guard_negative.py",
    ):
        errors = []
        gate._coverage_shape_attack(["core/risk_guard.py", test_path], errors)
        assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors


def test_gate_self_modification_fails_outside_bootstrap_branch():
    errors = []
    gate._governance_self_protection(
        ["scripts/run_adversarial_pr_gate.py"],
        "feature/ordinary-change",
        errors,
    )
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_REQUIRES_DEDICATED_RECERTIFICATION")


def test_gate_self_modification_allowed_only_for_bootstrap_branch():
    errors = []
    gate._governance_self_protection(
        list(gate.GATE_PROTECTED_PATHS),
        gate.BOOTSTRAP_BRANCH,
        errors,
    )
    assert errors == []


def test_syntax_attack_detects_invalid_python(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def broken(:\n    pass\n")
    errors = []
    gate._syntax_attack("candidate", ["core/foo.py"], errors)
    assert errors and errors[0].startswith("SYNTAX_ATTACK_FAIL:core/foo.py")


def test_dangerous_api_attack_detects_eval_exec_compile_import(monkeypatch):
    source = "\n".join(
        [
            "eval('1+1')",
            "exec('x=1')",
            "compile('x=1', '<x>', 'exec')",
            "__import__('os')",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._dangerous_api_attack("candidate", ["core/foo.py"], errors)
    assert any(":eval:" in e for e in errors)
    assert any(":exec:" in e for e in errors)
    assert any(":compile:" in e for e in errors)
    assert any(":__import__:" in e for e in errors)


def test_docs_only_change_does_not_require_test_change():
    errors = []
    gate._coverage_shape_attack(["docs/guide.md"], errors)
    assert errors == []


def test_test_files_are_not_classified_as_production_code():
    assert gate._is_test("tests/test_x.py")
    assert not gate._is_code("tests/test_x.py")
