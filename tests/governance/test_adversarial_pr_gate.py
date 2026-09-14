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
    assert "PRODUCTION_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_even_low_risk_production_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/analytics/foo.py", "tests/test_foo.py"], errors)
    assert "PRODUCTION_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_high_risk_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py", "tests/test_risk_guard.py"], errors)
    assert "PRODUCTION_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors
    assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_production_change_accepts_mutation_or_safety_test_name():
    for test_path in (
        "tests/test_risk_guard_mutation.py",
        "tests/test_risk_guard_safety.py",
        "tests/test_risk_guard_adversarial.py",
        "tests/test_risk_guard_negative.py",
        "tests/test_risk_guard_attack.py",
    ):
        errors = []
        gate._coverage_shape_attack(["core/risk_guard.py", test_path], errors)
        assert "PRODUCTION_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors
        assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors


def test_gate_self_modification_fails_outside_bootstrap_branch():
    errors = []
    gate._governance_self_protection(["scripts/run_adversarial_pr_gate.py"], "feature/ordinary-change", errors)
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_REQUIRES_DEDICATED_RECERTIFICATION")


def test_gate_self_modification_allowed_only_for_bootstrap_branch():
    errors = []
    gate._governance_self_protection(list(gate.GATE_PROTECTED_PATHS), gate.BOOTSTRAP_BRANCH, errors)
    assert errors == []


def test_syntax_attack_detects_invalid_python(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def broken(:\n    pass\n")
    errors = []
    gate._syntax_attack("candidate", ["core/foo.py"], errors)
    assert errors and errors[0].startswith("SYNTAX_ATTACK_FAIL:core/foo.py")


def test_dangerous_api_attack_detects_only_added_dangerous_calls(monkeypatch):
    diff = "\n".join(
        [
            "@@ -1,1 +1,4 @@",
            " context = compile(existing, '<x>', 'exec')",
            "+eval('1+1')",
            "+exec('x=1')",
            "+compile('x=1', '<x>', 'exec')",
            "+__import__('os')",
        ]
    )
    monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path: diff)
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert len(errors) == 4
    assert any(":eval:" in e for e in errors)
    assert any(":exec:" in e for e in errors)
    assert any(":compile:" in e for e in errors)
    assert any(":__import__:" in e for e in errors)


def test_preexisting_dangerous_call_does_not_fail_if_not_added(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n compile(existing, '<x>', 'exec')\n+safe_call()",
    )
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert errors == []


def test_added_skip_marker_is_detected(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1,2 @@\n+@pytest.mark.skip(reason='hide failure')\n+def test_x(): pass",
    )
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_SKIP_ADDED") for e in errors)


def test_assertion_removal_without_replacement_is_detected(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n-    assert result is False\n+    result",
    )
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_ASSERTION_LOSS") for e in errors)


def test_adversarial_file_with_pass_only_is_rejected(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def test_attack_rejects_bad_input():\n    pass\n")
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/foo.py", "tests/test_foo_adversarial.py"],
        errors,
    )
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_high_risk_change_requires_multiple_adversarial_checks(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert value is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"],
        errors,
    )
    assert any(e.startswith("ADVERSARIAL_TEST_TOO_SHALLOW") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_substantive_low_risk_adversarial_case_passes_quality_floor(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    result = False\n    assert result is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack(
        "candidate",
        ["core/analytics/foo.py", "tests/test_foo_adversarial.py"],
        errors,
    )
    assert errors == []


def test_docs_only_change_does_not_require_test_change():
    errors = []
    gate._coverage_shape_attack(["docs/guide.md"], errors)
    assert errors == []


def test_test_files_are_not_classified_as_production_code():
    assert gate._is_test("tests/test_x.py")
    assert not gate._is_code("tests/test_x.py")


def test_adversarial_test_name_detection_is_explicit():
    assert gate._is_adversarial_test("tests/test_order_safety.py")
    assert gate._is_adversarial_test("tests/test_math_negative.py")
    assert not gate._is_adversarial_test("tests/test_happy_path.py")
