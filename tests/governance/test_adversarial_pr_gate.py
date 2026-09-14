from scripts import run_adversarial_pr_gate as gate


def test_high_risk_classification_covers_execution_risk_strategies_and_workflows():
    assert gate._high_risk("main.py")
    assert gate._high_risk("core/execution_engine.py")
    assert gate._high_risk("core/risk_engine.py")
    assert gate._high_risk("core/feed/supervisor.py")
    assert gate._high_risk("strategies/foo.py")
    assert gate._high_risk(".github/workflows/ci.yml")
    assert not gate._high_risk("docs/readme.md")


def test_main_and_config_are_real_production_code_not_classification_bypasses():
    assert gate._is_code("main.py")
    assert gate._is_code("config/config.py")
    assert gate._requires_attack("main.py")
    assert gate._requires_attack("config/config.py")


def test_dependency_workflow_and_pytest_config_changes_require_attack_evidence():
    for path in (
        "requirements.txt",
        "pyproject.toml",
        "pytest.ini",
        "setup.cfg",
        "tox.ini",
        ".github/workflows/ci.yml",
    ):
        assert gate._requires_attack(path)
    assert not gate._requires_attack("docs/guide.md")


def test_attack_required_change_without_test_change_fails():
    errors = []
    gate._coverage_shape_attack(["core/foo.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_TEST_CHANGE" in errors
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_even_low_risk_production_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/analytics/foo.py", "tests/test_foo.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors


def test_high_risk_change_requires_adversarial_named_test():
    errors = []
    gate._coverage_shape_attack(["core/risk_guard.py", "tests/test_risk_guard.py"], errors)
    assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" in errors
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
        assert "ATTACK_REQUIRED_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors
        assert "HIGH_RISK_CHANGE_WITHOUT_ADVERSARIAL_TEST_FILE" not in errors


def test_gate_self_modification_fails_outside_bootstrap_branch(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection(
        "base", ["scripts/run_adversarial_pr_gate.py"], "feature/ordinary-change", errors
    )
    assert errors
    assert errors[0].startswith("ADVERSARIAL_GATE_SELF_MODIFICATION_BLOCKED_REQUIRES_TRUSTED_RECERTIFICATION")


def test_initial_bootstrap_is_allowed_only_when_base_has_no_gate(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: False)
    errors = []
    gate._governance_self_protection("base", list(gate.GATE_PROTECTED_PATHS), gate.BOOTSTRAP_BRANCH, errors)
    assert errors == []


def test_reusing_bootstrap_branch_after_gate_exists_is_blocked(monkeypatch):
    monkeypatch.setattr(gate, "_base_contains_gate", lambda base: True)
    errors = []
    gate._governance_self_protection("base", list(gate.GATE_PROTECTED_PATHS), gate.BOOTSTRAP_BRANCH, errors)
    assert errors


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


def test_indirect_getattr_eval_lookup_is_detected(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: '@@ -0,0 +1 @@\n+fn = getattr(builtins, "eval")',
    )
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert any(e.startswith("DANGEROUS_API_INDIRECT_LOOKUP_ADDED") for e in errors)


def test_preexisting_dangerous_call_does_not_fail_if_not_added(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n compile(existing, '<x>', 'exec')\n+safe_call()",
    )
    errors = []
    gate._dangerous_api_attack("base", "candidate", ["core/foo.py"], errors)
    assert errors == []


def test_added_skip_and_xfail_forms_are_detected(monkeypatch):
    for added in (
        "+@pytest.mark.skip(reason='hide failure')",
        "+pytest.skip('hide failure')",
        "+pytest.xfail('hide failure')",
        "+@pytest.mark.xfail(reason='hide failure')",
    ):
        monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}")
        errors = []
        gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
        assert any(e.startswith("TEST_WEAKENING_SKIP_OR_XFAIL_ADDED") for e in errors)


def test_trivial_assertion_and_broad_exception_are_detected(monkeypatch):
    diff = "@@ -0,0 +1,2 @@\n+assert True\n+with pytest.raises(Exception):"
    monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path: diff)
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_TRIVIAL_ASSERT_ADDED") for e in errors)
    assert any(e.startswith("TEST_WEAKENING_BROAD_EXCEPTION_ASSERTION") for e in errors)


def test_assertion_removal_without_replacement_is_detected(monkeypatch):
    monkeypatch.setattr(
        gate,
        "changed_diff",
        lambda base, candidate, path: "@@ -1 +1 @@\n-    assert result is False\n+    result",
    )
    errors = []
    gate._test_weakening_attack("base", "candidate", ["tests/test_x.py"], errors)
    assert any(e.startswith("TEST_WEAKENING_ASSERTION_LOSS") for e in errors)


def test_pytest_collection_suppression_changes_are_blocked(monkeypatch):
    for added in (
        "+addopts = --ignore=tests/integration",
        "+addopts = --deselect=tests/test_x.py::test_bad",
        "+testpaths = tests/small_subset",
        "+python_files = test_only_easy_cases.py",
    ):
        monkeypatch.setattr(gate, "changed_diff", lambda base, candidate, path, line=added: f"@@ -0,0 +1 @@\n{line}")
        errors = []
        gate._pytest_config_suppression_attack("base", "candidate", ["pyproject.toml"], errors)
        assert any(e.startswith("PYTEST_COLLECTION_OR_SUPPRESSION_CHANGE_REQUIRES_EXPLICIT_RECERTIFICATION") for e in errors)


def test_adversarial_file_with_pass_only_is_rejected(monkeypatch):
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: "def test_attack_rejects_bad_input():\n    pass\n")
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)


def test_assert_true_does_not_satisfy_adversarial_quality_floor(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert True\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_self_equality_assertion_does_not_satisfy_quality_floor(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert result == result\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_broad_pytest_raises_does_not_count_as_substantive(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    with pytest.raises(Exception):\n        dangerous()\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_ASSERTION_FLOOR_FAIL") for e in errors)


def test_high_risk_change_requires_multiple_substantive_adversarial_checks(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    assert value is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors)
    assert any(e.startswith("ADVERSARIAL_TEST_TOO_SHALLOW") for e in errors)
    assert any(e.startswith("ADVERSARIAL_TEST_SUBSTANTIVE_CASE_FLOOR_FAIL") for e in errors)


def test_substantive_low_risk_adversarial_case_passes_quality_floor(monkeypatch):
    source = "def test_attack_rejects_bad_input():\n    result = False\n    assert result is False\n"
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/analytics/foo.py", "tests/test_foo_adversarial.py"], errors)
    assert errors == []


def test_two_substantive_high_risk_cases_pass_quality_floor(monkeypatch):
    source = "\n".join(
        [
            "def test_attack_rejects_bad_input():",
            "    assert rejected is True",
            "",
            "def test_boundary_blocks_missing_authority():",
            "    assert allowed is False",
        ]
    )
    monkeypatch.setattr(gate, "_read_candidate", lambda ref, path: source)
    errors = []
    gate._adversarial_test_quality_attack("candidate", ["core/risk_guard.py", "tests/test_risk_guard_adversarial.py"], errors)
    assert errors == []


def test_docs_only_change_does_not_require_test_change():
    errors = []
    gate._coverage_shape_attack(["docs/guide.md"], errors)
    assert errors == []


def test_test_files_are_not_classified_as_production_code():
    assert gate._is_test("tests/test_x.py")
    assert not gate._is_code("tests/test_x.py")
    assert not gate._requires_attack("tests/test_x.py")


def test_adversarial_test_name_detection_is_explicit():
    assert gate._is_adversarial_test("tests/test_order_safety.py")
    assert gate._is_adversarial_test("tests/test_math_negative.py")
    assert not gate._is_adversarial_test("tests/test_happy_path.py")
